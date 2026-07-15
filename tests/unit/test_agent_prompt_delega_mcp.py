"""Validate that AGENT_SYSTEM_PROMPT delegates selection to MCP."""

from app.prompts.agent_prompt import AGENT_SYSTEM_PROMPT


def test_prompt_contains_delegation_phrase():
    assert "fonte primária" in AGENT_SYSTEM_PROMPT, (
        "Prompt must contain 'fonte primária' to delegate to MCP"
    )


def test_prompt_contains_mcp_reference():
    assert "MCP" in AGENT_SYSTEM_PROMPT, (
        "Prompt must reference MCP"
    )


def test_prompt_max_50_lines():
    lines = [l for l in AGENT_SYSTEM_PROMPT.strip().splitlines() if l.strip()]
    assert len(lines) <= 50, (
        f"Prompt has {len(lines)} non-empty lines (max 50)"
    )


def test_prompt_contains_persona():
    assert "PI Chat" in AGENT_SYSTEM_PROMPT


def test_prompt_contains_time_reference():
    assert "Data/hora" in AGENT_SYSTEM_PROMPT
