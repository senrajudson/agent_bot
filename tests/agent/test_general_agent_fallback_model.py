"""Tests for Gemini model fallback in general_agent."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.exceptions import ServiceUnavailableError

from app.agent.general_agent import run_general_agent


def _mock_response(content: str = "resposta ok") -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


class TestGeneralAgentModelFallback:
    @pytest.mark.asyncio
    @patch("app.agent.shared.litellm.acompletion", new_callable=AsyncMock)
    @patch("app.agent.shared.settings")
    @patch("app.agent.general_agent.settings")
    async def test_uses_primary_model_first(self, mock_s_gen, mock_s_shared, mock_ac):
        mock_s_gen.LLM_PROVIDER = "gemini"
        mock_s_shared.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_s_shared.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
        mock_s_shared.GEMINI_API_KEY = "test-key"
        mock_ac.return_value = _mock_response("ok")

        result = await run_general_agent("oi")

        assert result["output"] == "ok"
        assert mock_ac.call_args.kwargs.get("model") == "gemini/gemini-3.1-flash-lite-preview"

    @pytest.mark.asyncio
    @patch("app.agent.shared.litellm.acompletion", new_callable=AsyncMock)
    @patch("app.agent.shared.settings")
    @patch("app.agent.general_agent.settings")
    async def test_falls_back_to_fallback_model_on_503(self, mock_s_gen, mock_s_shared, mock_ac):
        mock_s_gen.LLM_PROVIDER = "gemini"
        mock_s_shared.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_s_shared.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
        mock_s_shared.GEMINI_API_KEY = "test-key"

        def side_effect(**kwargs):
            model = kwargs.get("model", "")
            if "3.1-flash-lite" in model:
                raise ServiceUnavailableError("503", "gemini", "gemini-3.1-flash-lite-preview")
            return _mock_response("fallback ok")

        mock_ac.side_effect = side_effect

        result = await run_general_agent("oi")

        assert result["output"] == "fallback ok"
        assert mock_ac.call_count == 4  # 3 primary + 1 fallback

    @pytest.mark.asyncio
    @patch("app.agent.shared.litellm.acompletion", new_callable=AsyncMock)
    @patch("app.agent.shared.settings")
    @patch("app.agent.general_agent.settings")
    async def test_exhausts_both_models(self, mock_s_gen, mock_s_shared, mock_ac):
        mock_s_gen.LLM_PROVIDER = "gemini"
        mock_s_shared.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_s_shared.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
        mock_s_shared.GEMINI_API_KEY = "test-key"

        mock_ac.side_effect = ServiceUnavailableError("503", "gemini", "test-model")

        result = await run_general_agent("oi")

        assert "ServiceUnavailableError" in result["output"]
        assert mock_ac.call_count == 6  # 3 primary + 3 fallback

    @pytest.mark.asyncio
    @patch("app.agent.shared.litellm.acompletion", new_callable=AsyncMock)
    @patch("app.agent.shared.settings")
    @patch("app.agent.general_agent.settings")
    async def test_no_fallback_when_not_set(self, mock_s_gen, mock_s_shared, mock_ac):
        mock_s_gen.LLM_PROVIDER = "gemini"
        mock_s_shared.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_s_shared.GEMINI_FALLBACK_MODEL = None
        mock_s_shared.GEMINI_API_KEY = "test-key"

        mock_ac.side_effect = ServiceUnavailableError("503", "gemini", "test-model")

        result = await run_general_agent("oi")

        assert "ServiceUnavailableError" in result["output"]
        assert mock_ac.call_count == 3  # Only primary

    @pytest.mark.asyncio
    @patch("app.agent.shared.litellm.acompletion", new_callable=AsyncMock)
    @patch("app.agent.shared.settings")
    @patch("app.agent.general_agent.settings")
    async def test_fallback_skips_non_retryable_errors(self, mock_s_gen, mock_s_shared, mock_ac):
        mock_s_gen.LLM_PROVIDER = "gemini"
        mock_s_shared.GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
        mock_s_shared.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
        mock_s_shared.GEMINI_API_KEY = "test-key"

        mock_ac.side_effect = ValueError("bad request")

        result = await run_general_agent("oi")

        assert "ValueError" in result["output"]
        assert mock_ac.call_count == 1  # Non-retryable, no fallback
