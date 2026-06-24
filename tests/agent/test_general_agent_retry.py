"""Tests for general_agent retry logic with tenacity."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.exceptions import (
    APIConnectionError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from app.agent.general_agent import run_general_agent


def _mock_response(content: str = "resposta ok") -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


class TestGeneralAgentRetry:
    @pytest.mark.asyncio
    @patch("app.agent.general_agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_retries_on_service_unavailable(self, mock_acompletion):
        """503 on first 2 calls, success on 3rd."""
        mock_acompletion.side_effect = [
            ServiceUnavailableError("503", "gemini", "gemini-2.5-flash-lite"),
            ServiceUnavailableError("503", "gemini", "gemini-2.5-flash-lite"),
            _mock_response("ok after retry"),
        ]
        result = await run_general_agent("oi")

        assert result["output"] == "ok after retry"
        assert mock_acompletion.call_count == 3

    @pytest.mark.asyncio
    @patch("app.agent.general_agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_retries_on_rate_limit_error(self, mock_acompletion):
        mock_acompletion.side_effect = [
            RateLimitError("429", "gemini", "gemini-2.5-flash-lite"),
            _mock_response("ok"),
        ]
        result = await run_general_agent("oi")
        assert result["output"] == "ok"
        assert mock_acompletion.call_count == 2

    @pytest.mark.asyncio
    @patch("app.agent.general_agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_retries_on_api_connection_error(self, mock_acompletion):
        mock_acompletion.side_effect = [
            APIConnectionError("connection lost", "gemini", "gemini-2.5-flash-lite"),
            _mock_response("ok"),
        ]
        result = await run_general_agent("oi")
        assert result["output"] == "ok"
        assert mock_acompletion.call_count == 2

    @pytest.mark.asyncio
    @patch("app.agent.general_agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_retries_on_timeout(self, mock_acompletion):
        mock_acompletion.side_effect = [
            Timeout("request timed out", "gemini-2.5-flash-lite", "gemini"),
            _mock_response("ok"),
        ]
        result = await run_general_agent("oi")
        assert result["output"] == "ok"
        assert mock_acompletion.call_count == 2

    @pytest.mark.asyncio
    @patch("app.agent.general_agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_does_not_retry_on_bad_request(self, mock_acompletion):
        """Non-retryable errors should fail immediately."""
        mock_acompletion.side_effect = ValueError("bad request")
        result = await run_general_agent("oi")

        assert "Erro (ValueError)" in result["output"]
        assert mock_acompletion.call_count == 1

    @pytest.mark.asyncio
    @patch("app.agent.general_agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_exhausts_retries_and_returns_error_output(self, mock_acompletion):
        """After 3 retries, the error becomes the output (no sanitization)."""
        mock_acompletion.side_effect = ServiceUnavailableError(
            '{"error":{"code":503,"message":"high demand","status":"UNAVAILABLE"}}',
            "gemini",
            "gemini-2.5-flash-lite",
        )
        result = await run_general_agent("oi")

        assert "ServiceUnavailableError" in result["output"]
        assert "503" in result["output"]
        assert mock_acompletion.call_count == 3

    @pytest.mark.asyncio
    @patch("app.agent.general_agent.litellm.acompletion", new_callable=AsyncMock)
    async def test_success_on_first_try_no_retry(self, mock_acompletion):
        mock_acompletion.return_value = _mock_response("primeira tentativa")
        result = await run_general_agent("oi")

        assert result["output"] == "primeira tentativa"
        assert mock_acompletion.call_count == 1
