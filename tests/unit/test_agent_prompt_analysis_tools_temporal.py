"""Tests for system prompt temporal contract (T075-T076).

Validates that the prompt correctly documents the new temporal contract
for analyze_pi_tag_behavior and generate_pi_tags_analysis_report.
"""
from __future__ import annotations

import pytest


class TestPromptTemporalContract:
    """System prompt contains correct temporal instructions."""

    def test_prompt_contains_analyze_pi_with_formats(self):
        from app.prompts.agent_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "analyze_pi_tag_behavior" in prompt
        assert "ISO 8601 com offset" in prompt
        assert "*-24h" in prompt
        assert "*-1d" in prompt
        assert "T" in prompt
        assert "Y" in prompt

    def test_prompt_contains_report_with_formats(self):
        from app.prompts.agent_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "generate_pi_tags_analysis_report" in prompt
        assert "ISO 8601 com offset" in prompt

    def test_prompt_contains_invalid_timestamp_rule(self):
        from app.prompts.agent_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "INVALID_TIMESTAMP" in prompt
        assert "Não repita uma chamada" in prompt

    def test_prompt_does_not_contain_old_retry_rule(self):
        from app.prompts.agent_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "Não repita a chamada convertendo-os para ISO após erro" not in prompt

    def test_prompt_contains_normalization_note(self):
        from app.prompts.agent_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "Tokens PI válidos são normalizados internamente pela tool" in prompt

    def test_prompt_preserves_schema_first_rules(self):
        from app.prompts.agent_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "context_text" in prompt
        assert "pergunta_usuario" in prompt
        assert "NÃO envie" in prompt

    def test_prompt_contains_tag_statistics_still(self):
        from app.prompts.agent_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "tag_statistics" in prompt
