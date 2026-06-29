"""Tests for agent retry logic and _classify_error."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from litellm.exceptions import (
    APIConnectionError,
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from app.agent.agent import _classify_error


class TestClassifyError:
    def test_service_unavailable_returns_friendly_message(self):
        error = ServiceUnavailableError("503 UNAVAILABLE", "gemini", "gemini-2.5-flash-lite")
        result = _classify_error(error)
        assert "temporariamente indisponível" in result
        assert "503" not in result

    def test_api_connection_error_returns_friendly_message(self):
        error = APIConnectionError("connection refused", "gemini", "gemini-2.5-flash-lite")
        result = _classify_error(error)
        assert "temporariamente indisponível" in result

    def test_timeout_returns_friendly_message(self):
        error = Timeout("request timed out", "gemini-2.5-flash-lite", "gemini")
        result = _classify_error(error)
        assert "temporariamente indisponível" in result

    def test_rate_limit_returns_overloaded_message(self):
        error = RateLimitError("429 rate limit", "gemini", "gemini-2.5-flash-lite")
        result = _classify_error(error)
        assert "sobrecarregado" in result

    def test_authentication_error_returns_config_message(self):
        error = AuthenticationError("401 invalid key", "gemini", "gemini-2.5-flash-lite")
        result = _classify_error(error)
        assert "Chave de API" in result

    def test_recursion_error_returns_reformulate_message(self):
        error = RecursionError("max recursion")
        result = _classify_error(error)
        assert "reformular" in result

    def test_closed_resource_error_returns_mcp_message(self):
        """ClosedResourceError has type name 'ClosedResourceError'."""

        class ClosedResourceError(Exception):
            pass

        error = ClosedResourceError("something")
        result = _classify_error(error)
        assert "ferramentas (MCP)" in result

    def test_generic_error_returns_error_type(self):
        error = ValueError("something broke")
        result = _classify_error(error)
        assert "ValueError" in result
        assert "something broke" in result

    def test_service_unavailable_in_503_message(self):
        error = Exception("ServiceUnavailableError: 503 UNAVAILABLE")
        result = _classify_error(error)
        assert "temporariamente indisponível" in result

    def test_503_in_message_returns_friendly(self):
        error = Exception("Error 503 from upstream")
        result = _classify_error(error)
        assert "temporariamente indisponível" in result
