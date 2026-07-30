"""Validate INVALID_TOOL_ARGUMENTS detection, classification, and blocking."""

from typing import Any

from app.agent.agent import (
    _classify_error,
    _detect_invalid_tool_arguments_loop,
    _extract_tool_name_from_error,
    _is_sanitized_tool_name,
    _is_validation_error_response,
)

_VALIDATION_ERROR_MSG = (
    "1 validation error for call[status_pims_tool]\n"
    "context_text\n"
    "  Unexpected keyword argument "
    "[type=unexpected_keyword_argument, input_value='Verificação de saúde...', input_type=str]"
)

_GENERIC_ERROR_MSG = "Não consegui executar a consulta."


# ---------------------------------------------------------------------------
# _extract_tool_name_from_error
# ---------------------------------------------------------------------------

def test_extract_tool_name_success():
    name = _extract_tool_name_from_error(_VALIDATION_ERROR_MSG)
    assert name == "status_pims_tool"


def test_extract_tool_name_none():
    name = _extract_tool_name_from_error("some random error message without pattern")
    assert name is None


def test_extract_tool_name_malicious_input():
    name = _extract_tool_name_from_error("call[../etc/passwd]")
    assert name is None  # regex doesn't match dots/slashes


def test_extract_tool_name_empty():
    name = _extract_tool_name_from_error("call[]")
    assert name is None


# ---------------------------------------------------------------------------
# _is_sanitized_tool_name
# ---------------------------------------------------------------------------

def test_sanitized_name_valid():
    assert _is_sanitized_tool_name("status_pims_tool") is True


def test_sanitized_name_with_dots():
    assert _is_sanitized_tool_name("../etc/passwd") is False


def test_sanitized_name_with_spaces():
    assert _is_sanitized_tool_name("bad name") is False


def test_sanitized_name_empty():
    assert _is_sanitized_tool_name("") is False


def test_sanitized_name_none():
    assert _is_sanitized_tool_name(None) is False  # type: ignore[arg-type]


def test_sanitized_name_uppercase():
    assert _is_sanitized_tool_name("UPPERCASE") is False


# ---------------------------------------------------------------------------
# _is_validation_error_response
# ---------------------------------------------------------------------------

def test_validation_error_response_known_keywords():
    for msg in [
        "Unexpected keyword argument",
        "Extra inputs are not permitted",
        "ValidationError",
    ]:
        assert _is_validation_error_response(msg), f"Should detect: {msg}"


def test_validation_error_response_case_insensitive():
    assert _is_validation_error_response("UNEXPECTED KEYWORD ARGUMENT") is True


def test_validation_error_response_none():
    assert _is_validation_error_response(None) is False


def test_validation_error_response_connect_error():
    assert _is_validation_error_response("ConnectError: connection refused") is False


def test_validation_error_response_timeout():
    assert _is_validation_error_response("timeout") is False


# ---------------------------------------------------------------------------
# _detect_invalid_tool_arguments_loop
# ---------------------------------------------------------------------------

def _make_tool_call_msg(name: str, args: dict | None = None) -> dict[str, Any]:
    return {
        "role": "assistant",
        "tool_calls": [{"name": name, "args": args or {}}],
    }


def _make_tool_response_msg(name: str, response: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_responses": [{"name": name, "response": response}],
    }


def _make_agent_response(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def test_block_on_second_invalid_attempt():
    """Two validation errors for the same tool must block."""
    messages = [
        _make_tool_call_msg("status_pims_tool", {"context_text": "x"}),
        _make_tool_response_msg("status_pims_tool", _VALIDATION_ERROR_MSG),
        _make_tool_call_msg("status_pims_tool", {"context_text": "y"}),
        _make_tool_response_msg("status_pims_tool", _VALIDATION_ERROR_MSG),
    ]
    result = _detect_invalid_tool_arguments_loop(messages)
    assert result["blocked"] is True
    assert result["tool_name"] == "status_pims_tool"
    assert "status_pims_tool" in result["output"]


def test_allow_on_single_invalid_attempt():
    """Single validation error must not block (allows one retry)."""
    messages = [
        _make_tool_call_msg("status_pims_tool", {"context_text": "x"}),
        _make_tool_response_msg("status_pims_tool", _VALIDATION_ERROR_MSG),
    ]
    result = _detect_invalid_tool_arguments_loop(messages)
    assert result["blocked"] is False


def test_allow_on_two_different_tools():
    """Validation errors for different tools must not block."""
    messages = [
        _make_tool_call_msg("tool_a", {"context_text": "x"}),
        _make_tool_response_msg("tool_a", _VALIDATION_ERROR_MSG),
        _make_tool_call_msg("tool_b", {"context_text": "y"}),
        _make_tool_response_msg("tool_b", _VALIDATION_ERROR_MSG),
    ]
    result = _detect_invalid_tool_arguments_loop(messages)
    assert result["blocked"] is False


def test_allow_on_corrected_call():
    """Second call with fixed arguments must not block if no error returned."""
    messages = [
        _make_tool_call_msg("status_pims_tool", {"context_text": "x"}),
        _make_tool_response_msg("status_pims_tool", _VALIDATION_ERROR_MSG),
        _make_tool_call_msg("status_pims_tool", {}),
        _make_tool_response_msg("status_pims_tool", '{"available":true}'),
    ]
    result = _detect_invalid_tool_arguments_loop(messages)
    assert result["blocked"] is False


def test_no_false_positive_connection_error():
    """ConnectError must not be detected as validation error."""
    messages = [
        _make_tool_call_msg("status_pims_tool", {}),
        _make_tool_response_msg(
            "status_pims_tool",
            "ConnectError: connection refused",
        ),
    ]
    result = _detect_invalid_tool_arguments_loop(messages)
    assert result["blocked"] is False


def test_message_sanitized():
    """Blocked output must not contain argument values, context_text, etc."""
    messages = [
        _make_tool_call_msg("status_pims_tool", {"context_text": "x"}),
        _make_tool_response_msg("status_pims_tool", _VALIDATION_ERROR_MSG),
        _make_tool_call_msg("status_pims_tool", {"context_text": "y"}),
        _make_tool_response_msg("status_pims_tool", _VALIDATION_ERROR_MSG),
    ]
    result = _detect_invalid_tool_arguments_loop(messages)
    output = result["output"]
    assert "context_text" not in output
    assert "x" not in output
    assert "y" not in output


# ---------------------------------------------------------------------------
# _classify_error
# ---------------------------------------------------------------------------

def test_classify_validation_error_names_tool():
    msg = _classify_error(Exception(_VALIDATION_ERROR_MSG))
    assert "status_pims_tool" in msg
    assert "schema" in msg.lower()
    assert "Use somente os campos" in msg


def test_classify_validation_error_generic_fallback():
    msg = _classify_error(Exception("ValidationError: Field required"))
    assert "schema" in msg.lower()
    assert "Use somente os campos" in msg


def test_classify_connect_error_not_validation():
    msg = _classify_error(ConnectionError("ConnectError: connection failed"))
    assert "schema" not in msg.lower()
