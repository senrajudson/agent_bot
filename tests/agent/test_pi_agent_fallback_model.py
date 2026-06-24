"""Tests for Gemini model fallback in pi_agent."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.exceptions import ServiceUnavailableError

from app.agent.pi_agent import _classify_error, run_pi_agent


class TestClassifyErrorUnchanged:
    def test_service_unavailable_returns_friendly(self):
        error = ServiceUnavailableError("503", "gemini", "test-model")
        result = _classify_error(error)
        assert "temporariamente indisponível" in result

    def test_rate_limit_returns_overloaded(self):
        from litellm.exceptions import RateLimitError
        error = RateLimitError("429", "gemini", "test-model")
        result = _classify_error(error)
        assert "sobrecarregado" in result

    def test_generic_error_returns_error_type(self):
        error = ValueError("something broke")
        result = _classify_error(error)
        assert "ValueError" in result


class TestPiAgentModelFallback:
    @pytest.mark.asyncio
    @patch("app.agent.pi_agent._run_pi_agent_core", new_callable=AsyncMock)
    @patch("app.agent.pi_agent.settings")
    async def test_uses_primary_model(self, mock_settings, mock_core):
        mock_settings.LLM_PROVIDER = "gemini"
        mock_settings.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_settings.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
        mock_core.return_value = {"messages": [], "output": "ok", "error": None}

        result = await run_pi_agent("test", user_id="u1")

        assert result["output"] == "ok"
        assert mock_core.call_count == 1
        call_kwargs = mock_core.call_args.kwargs
        assert call_kwargs["model_name"] == "gemini-3.1-flash-lite-preview"

    @pytest.mark.asyncio
    @patch("app.agent.pi_agent._run_pi_agent_core", new_callable=AsyncMock)
    @patch("app.agent.pi_agent.settings")
    async def test_falls_back_on_503(self, mock_settings, mock_core):
        mock_settings.LLM_PROVIDER = "gemini"
        mock_settings.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_settings.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

        call_count = [0]

        async def core_side_effect(*args, **kwargs):
            call_count[0] += 1
            model = kwargs.get("model_name")
            if model == "gemini-3.1-flash-lite-preview":
                raise ServiceUnavailableError("503", "gemini", model)
            return {"messages": [], "output": "fallback ok", "error": None}

        mock_core.side_effect = core_side_effect

        result = await run_pi_agent("test", user_id="u1")

        assert result["output"] == "fallback ok"
        # 3 retries on primary + 1 on fallback
        assert mock_core.call_count == 4

    @pytest.mark.asyncio
    @patch("app.agent.pi_agent._run_pi_agent_core", new_callable=AsyncMock)
    @patch("app.agent.pi_agent.settings")
    async def test_exhausts_both_models(self, mock_settings, mock_core):
        mock_settings.LLM_PROVIDER = "gemini"
        mock_settings.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_settings.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

        mock_core.side_effect = ServiceUnavailableError("503", "gemini", "test")

        result = await run_pi_agent("test", user_id="u1")

        assert "temporariamente indisponível" in result["output"]
        assert mock_core.call_count == 6  # 3 primary + 3 fallback

    @pytest.mark.asyncio
    @patch("app.agent.pi_agent._run_pi_agent_core", new_callable=AsyncMock)
    @patch("app.agent.pi_agent.settings")
    async def test_no_fallback_when_not_set(self, mock_settings, mock_core):
        mock_settings.LLM_PROVIDER = "gemini"
        mock_settings.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_settings.GEMINI_FALLBACK_MODEL = None

        mock_core.side_effect = ServiceUnavailableError("503", "gemini", "test")

        result = await run_pi_agent("test", user_id="u1")

        assert mock_core.call_count == 3  # Only primary

    @pytest.mark.asyncio
    @patch("app.agent.pi_agent._run_pi_agent_core", new_callable=AsyncMock)
    @patch("app.agent.pi_agent.settings")
    async def test_non_gemini_provider_skips_fallback(self, mock_settings, mock_core):
        mock_settings.LLM_PROVIDER = "ollama"
        mock_core.return_value = {"messages": [], "output": "ok", "error": None}

        result = await run_pi_agent("test", user_id="u1")

        assert result["output"] == "ok"
        # model_name=None means use default get_llm (no fallback logic)
        assert mock_core.call_args.kwargs["model_name"] is None
