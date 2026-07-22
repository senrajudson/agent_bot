"""Validate that AGENT_SYSTEM_PROMPT delegates selection to MCP."""

from app.prompts.agent_prompt import build_system_prompt


def get_prompt(**kwargs):
    return build_system_prompt(**kwargs)


# Default prompt (both flags false)


def test_prompt_contains_delegation_phrase():
    prompt = get_prompt()
    assert "fonte primária" in prompt


def test_prompt_contains_mcp_reference():
    prompt = get_prompt()
    assert "MCP" in prompt


def test_prompt_max_50_lines():
    prompt = get_prompt()
    lines = [l for l in prompt.strip().splitlines() if l.strip()]
    assert len(lines) <= 50


def test_prompt_contains_persona():
    prompt = get_prompt()
    assert "PI Chat" in prompt


def test_prompt_contains_time_reference():
    prompt = get_prompt()
    assert "Data/hora" in prompt


def test_prompt_default_omits_csv_artifact_tool():
    prompt = get_prompt()
    assert "create_csv_artifact_tool" not in prompt


def test_prompt_negative_csv_rule_present_when_disabled():
    prompt = get_prompt(enable_drive_csv_export_tool=False)
    assert "exportação em CSV não está disponível" in prompt


# Drive CSV disabled (default)


def test_drive_csv_omitted_when_disabled():
    prompt = get_prompt(enable_drive_csv_export_tool=False)
    assert "export_csv_to_drive_tool" not in prompt


def test_drive_csv_negative_rule_when_disabled():
    prompt = get_prompt(enable_drive_csv_export_tool=False)
    assert "não está disponível" in prompt


# Drive CSV enabled


def test_drive_csv_present_when_enabled():
    prompt = get_prompt(enable_drive_csv_export_tool=True)
    assert "export_csv_to_drive_tool" in prompt


def test_drive_csv_removes_negative_rule():
    prompt = get_prompt(enable_drive_csv_export_tool=True)
    assert "não está disponível" not in prompt


def test_drive_csv_positive_rule_instead():
    prompt = get_prompt(enable_drive_csv_export_tool=True)
    assert "após obter os dados" in prompt


def test_drive_csv_mentions_view_url():
    prompt = get_prompt(enable_drive_csv_export_tool=True)
    assert "view_url" in prompt


def test_drive_csv_does_not_invent_url():
    prompt = get_prompt(enable_drive_csv_export_tool=True)
    assert "não invente URL" in prompt or "Não invente URL" in prompt


def test_drive_csv_limits_500():
    prompt = get_prompt(enable_drive_csv_export_tool=True)
    assert "500" in prompt


def test_max_lines_with_drive_enabled():
    prompt = get_prompt(enable_drive_csv_export_tool=True)
    lines = [l for l in prompt.strip().splitlines() if l.strip()]
    assert len(lines) <= 50


# Coexistence with test artifact tool


def test_coexistence_both_enabled():
    prompt = get_prompt(
        enable_test_artifact_tool=True,
        enable_drive_csv_export_tool=True,
    )
    assert "generate_test_artifact_tool" in prompt
    assert "export_csv_to_drive_tool" in prompt
    assert "não está disponível" not in prompt
