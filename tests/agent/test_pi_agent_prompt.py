"""
Agent behavior tests for the PI agent prompt.

Tests that the system prompt correctly guides the LLM to choose
pi_request with the right filter for different user query types.
"""

import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.prompts.pi_agent_prompt import AGENT_SYSTEM_PROMPT


class TestPromptContainsPiRequest:
    def test_pi_request_mentioned(self):
        assert "pi_request" in AGENT_SYSTEM_PROMPT

    def test_no_consultar_tag(self):
        assert "consultar_tag" not in AGENT_SYSTEM_PROMPT

    def test_tag_statistics_retained(self):
        assert "tag_statistics" in AGENT_SYSTEM_PROMPT

    def test_tag_calculus_retained(self):
        assert "tag_calculus" in AGENT_SYSTEM_PROMPT

    def test_status_pims_retained(self):
        assert "status_pims" in AGENT_SYSTEM_PROMPT


class TestPromptWhitelistInPrompt:
    """Verify the prompt includes all expected path templates."""

    EXPECTED_TEMPLATES = [
        "/points",
        "/points/{WebId}",
        "/points/{WebId}/attributes",
        "/streams/{WebId}/value",
        "/streams/{WebId}/recorded",
        "/streams/{WebId}/interpolated",
        "/streams/{WebId}/summary",
        "/streams/{WebId}/plot",
        "/dataservers",
        "/dataservers/{WebId}/points",
        "/dataservers/{WebId}/enumerationsets",
        "/enumerationsets/{WebId}/enumerationvalues",
        "/streamsets/value",
        "/streamsets/recorded",
        "/streamsets/interpolated",
        "/batch",
    ]

    @pytest.mark.parametrize("template", EXPECTED_TEMPLATES)
    def test_template_in_prompt(self, template):
        assert template in AGENT_SYSTEM_PROMPT, (
            f"Template '{template}' not found in system prompt"
        )


class TestPromptSearchGuidance:
    def test_descriptor_filter_mentioned(self):
        assert "descriptorFilter" in AGENT_SYSTEM_PROMPT

    def test_name_filter_mentioned(self):
        assert "nameFilter" in AGENT_SYSTEM_PROMPT

    def test_instrumenttag_filter_mentioned(self):
        assert "instrumenttagFilter" in AGENT_SYSTEM_PROMPT

    def test_max_count_rule(self):
        assert "maxCount" in AGENT_SYSTEM_PROMPT

    def test_disambiguation_rule(self):
        assert "mais específic" in AGENT_SYSTEM_PROMPT.lower() or "específic" in AGENT_SYSTEM_PROMPT.lower()


class TestPromptCriteriaTable:
    def test_search_criterion_present(self):
        assert "Busca de tags" in AGENT_SYSTEM_PROMPT or "busca" in AGENT_SYSTEM_PROMPT.lower()

    def test_stream_criterion(self):
        assert "streams" in AGENT_SYSTEM_PROMPT.lower() or "stream" in AGENT_SYSTEM_PROMPT.lower()

    def test_aggregation_criterion(self):
        assert "tag_statistics" in AGENT_SYSTEM_PROMPT


class TestPromptResponseRules:
    def test_concise_response(self):
        assert "direto e conciso" in AGENT_SYSTEM_PROMPT.lower() or "conciso" in AGENT_SYSTEM_PROMPT.lower()

    def test_no_asterisks(self):
        assert "asteriscos duplos" in AGENT_SYSTEM_PROMPT.lower()

    def test_portuguese_response(self):
        assert "português" in AGENT_SYSTEM_PROMPT.lower()

    def test_list_format(self):
        assert "hífen" in AGENT_SYSTEM_PROMPT.lower() or "lista" in AGENT_SYSTEM_PROMPT.lower()


class TestBypassStateInjection:
    """Verify the agent uses a callable instruction to bypass ADK state injection.

    ADK's inject_session_state runs regex r'{+[^{}]*}+' on the instruction string.
    Our prompt contains {WebId} in path templates, which would trigger
    'Context variable not found: WebId' if state injection is not bypassed.
    """

    def test_instruction_is_callable(self):
        from app.agent.pi_agent import _build_pi_agent

        agent = _build_pi_agent()
        assert not isinstance(agent.instruction, str)
        assert callable(agent.instruction)

    @pytest.mark.asyncio
    async def test_instruction_returns_prompt(self):
        from app.agent.pi_agent import _build_pi_agent
        from google.adk.agents.readonly_context import ReadonlyContext

        agent = _build_pi_agent()
        mock_ctx = AsyncMock(spec=ReadonlyContext)
        result = agent.instruction(mock_ctx)
        if inspect.isawaitable(result):
            result = await result
        assert result == AGENT_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_canonical_instruction_bypasses_state_injection(self):
        from app.agent.pi_agent import _build_pi_agent
        from google.adk.agents.readonly_context import ReadonlyContext

        agent = _build_pi_agent()
        mock_ctx = AsyncMock(spec=ReadonlyContext)
        prompt, bypass = await agent.canonical_instruction(mock_ctx)
        assert bypass is True
        assert prompt == AGENT_SYSTEM_PROMPT

    def test_prompt_contains_braces_that_would_trigger_injection(self):
        """Sanity check: the prompt contains {WebId} which confirms
        the bypass is necessary (not just a no-op)."""
        assert "{WebId}" in AGENT_SYSTEM_PROMPT
