"""Tests for app.infrastructure.outbox._error_redaction."""
from __future__ import annotations

import pytest

from app.infrastructure.outbox._error_redaction import (
    REDACTED_TOKEN,
    TRUNCATED_SUFFIX,
    sanitize_error_message,
    sanitize_exception,
)


# ---------------------------------------------------------------------------
# Normal / edge cases
# ---------------------------------------------------------------------------


def test_normal_message_preserved() -> None:
    msg = "simulated redis failure"
    assert sanitize_error_message(msg) == msg


def test_empty_string() -> None:
    assert sanitize_error_message("") == ""


def test_none() -> None:
    assert sanitize_error_message(None) == ""


# ---------------------------------------------------------------------------
# user_message
# ---------------------------------------------------------------------------


def test_user_message_eq_form() -> None:
    result = sanitize_error_message("user_message=secret text")
    assert result == "user_message=<REDACTED> text"


def test_user_message_colon_form() -> None:
    result = sanitize_error_message("user_message: secret text")
    assert result == "user_message: <REDACTED> text"


def test_user_message_json_form() -> None:
    result = sanitize_error_message('"user_message": "secret text"')
    assert result == '"user_message": <REDACTED>'


# ---------------------------------------------------------------------------
# assistant_message
# ---------------------------------------------------------------------------


def test_assistant_message() -> None:
    result = sanitize_error_message("assistant_message=ola mundo")
    assert result == "assistant_message=<REDACTED> mundo"


# ---------------------------------------------------------------------------
# token
# ---------------------------------------------------------------------------


def test_token() -> None:
    result = sanitize_error_message("token=abc.def.ghi")
    assert result == "token=<REDACTED>"


# ---------------------------------------------------------------------------
# password / passwd
# ---------------------------------------------------------------------------


def test_password() -> None:
    result = sanitize_error_message("password=hunter2")
    assert result == "password=<REDACTED>"


def test_passwd() -> None:
    result = sanitize_error_message("passwd=secret123")
    assert result == "passwd=<REDACTED>"


# ---------------------------------------------------------------------------
# secret
# ---------------------------------------------------------------------------


def test_secret() -> None:
    result = sanitize_error_message("secret=shh")
    assert result == "secret=<REDACTED>"


# ---------------------------------------------------------------------------
# api_key
# ---------------------------------------------------------------------------


def test_api_key() -> None:
    result = sanitize_error_message("api_key=xyz123abc")
    assert result == "api_key=<REDACTED>"


# ---------------------------------------------------------------------------
# authorization / bearer
# ---------------------------------------------------------------------------


def test_authorization_header() -> None:
    result = sanitize_error_message("authorization: Bearer abc.def.ghi")
    assert result == "authorization: <REDACTED>"


def test_authorization_basic() -> None:
    result = sanitize_error_message("authorization=basic-token")
    assert result == "authorization=<REDACTED>"


def test_bearer_standalone() -> None:
    result = sanitize_error_message("Bearer abc.def.ghi")
    assert result == "Bearer <REDACTED>"


def test_bearer_lowercase() -> None:
    result = sanitize_error_message("bearer mytoken123")
    assert result == "bearer <REDACTED>"


# ---------------------------------------------------------------------------
# Multiple secrets
# ---------------------------------------------------------------------------


def test_multiple_secrets() -> None:
    result = sanitize_error_message(
        "user_message=hello token=abc secret=shh"
    )
    assert "user_message=<REDACTED>" in result
    assert "token=<REDACTED>" in result
    assert "secret=<REDACTED>" in result


# ---------------------------------------------------------------------------
# Case-insensitive key matching
# ---------------------------------------------------------------------------


def test_case_insensitive() -> None:
    result = sanitize_error_message("User_Message=secret TOKEN=abc")
    assert "User_Message=<REDACTED>" in result
    assert "TOKEN=<REDACTED>" in result


# ---------------------------------------------------------------------------
# Quoted values
# ---------------------------------------------------------------------------


def test_quoted_value_double() -> None:
    result = sanitize_error_message('token="abc def ghi"')
    assert result == 'token=<REDACTED>'


def test_quoted_value_single() -> None:
    result = sanitize_error_message("token='abc def ghi'")
    assert result == 'token=<REDACTED>'


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def test_truncation_long_message() -> None:
    long = "a" * 5000
    result = sanitize_error_message(long, max_length=100)
    expected_len = 100 - len(TRUNCATED_SUFFIX)
    assert len(result) <= 100
    assert result.endswith(TRUNCATED_SUFFIX)
    assert result[:expected_len] == "a" * expected_len


def test_truncation_with_redaction() -> None:
    payload = "user_message=y " + "a" * 5000
    result = sanitize_error_message(payload, max_length=100)
    assert len(result) <= 100
    assert result.endswith(TRUNCATED_SUFFIX)
    assert REDACTED_TOKEN in result


# ---------------------------------------------------------------------------
# sanitize_exception
# ---------------------------------------------------------------------------


def test_sanitize_exception_preserves_technical() -> None:
    exc = RuntimeError("simulated redis failure")
    result = sanitize_exception(exc)
    assert "simulated redis failure" in result


def test_sanitize_exception_redacts() -> None:
    exc = RuntimeError("user_message=leaked")
    result = sanitize_exception(exc)
    assert "user_message=<REDACTED>" in result
    assert "leaked" not in result


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


def test_idempotent() -> None:
    original = "user_message=hello token=world"
    first = sanitize_error_message(original)
    second = sanitize_error_message(first)
    assert first == second
