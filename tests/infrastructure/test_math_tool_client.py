"""Tests for Math Tool client retry logic and error handling."""
from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from domain.analytics.clients.math_tool_client import (
    _RETRYABLE_ERRORS,
    _TIMEOUT,
    _post_math_tool,
    call_calculate,
    call_calculus,
    call_stats,
)


# =========================================================================
# Helpers
# =========================================================================

def _make_httpx_connect_error(msg: str = "Temporary failure in name resolution") -> httpx.ConnectError:
    return httpx.ConnectError(msg)


def _make_gaierror() -> socket.gaierror:
    return socket.gaierror(-3, "Temporary failure in name resolution")


def _make_httpx_read_timeout() -> httpx.ReadTimeout:
    return httpx.ReadTimeout("read timed out")


def _make_httpx_pool_timeout() -> httpx.PoolTimeout:
    return httpx.PoolTimeout("pool timeout")


def _make_connection_refused() -> httpx.ConnectError:
    return httpx.ConnectError("[Errno 111] Connection refused")


# =========================================================================
# Retryable errors tuple
# =========================================================================

class TestRetryableErrors:
    def test_connect_error_is_retryable(self) -> None:
        assert issubclass(httpx.ConnectError, _RETRYABLE_ERRORS)

    def test_connect_timeout_is_retryable(self) -> None:
        assert issubclass(httpx.ConnectTimeout, _RETRYABLE_ERRORS)

    def test_read_timeout_is_retryable(self) -> None:
        assert issubclass(httpx.ReadTimeout, _RETRYABLE_ERRORS)

    def test_pool_timeout_is_retryable(self) -> None:
        assert issubclass(httpx.PoolTimeout, _RETRYABLE_ERRORS)

    def test_gaierror_is_retryable(self) -> None:
        assert issubclass(socket.gaierror, _RETRYABLE_ERRORS)

    def test_http_status_error_is_not_retryable(self) -> None:
        assert not issubclass(httpx.HTTPStatusError, _RETRYABLE_ERRORS)

    def test_json_error_is_not_retryable(self) -> None:
        import json as _json
        assert not issubclass(_json.JSONDecodeError, _RETRYABLE_ERRORS)


# =========================================================================
# _post_math_tool — retry behavior
# =========================================================================

class TestPostMathToolRetry:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"sum": 15.0}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domain.analytics.clients.math_tool_client.httpx.AsyncClient", return_value=mock_client):
            result = await _post_math_tool("/stats", {"values": [1, 2, 3], "operations": ["sum"]})

        assert result["ok"] is True
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_connect_error_then_success(self) -> None:
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_httpx_connect_error()
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"ok": True}
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = AsyncMock()
        mock_client.post.side_effect = side_effect
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domain.analytics.clients.math_tool_client.httpx.AsyncClient", return_value=mock_client):
            result = await _post_math_tool("/stats", {"values": [1]})

        assert result["ok"] is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_gaierror_then_success(self) -> None:
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise _make_gaierror()
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"ok": True}
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = AsyncMock()
        mock_client.post.side_effect = side_effect
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domain.analytics.clients.math_tool_client.httpx.AsyncClient", return_value=mock_client):
            result = await _post_math_tool("/calculate", {"expression": "1+1"})

        assert result["ok"] is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_on_persistent_network_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_httpx_connect_error("DNS resolution failed")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domain.analytics.clients.math_tool_client.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.ConnectError):
                await _post_math_tool("/stats", {"values": [1]})

        # 3 attempts total
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_http_status_error(self) -> None:
        resp = MagicMock()
        resp.status_code = 422
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unprocessable Entity",
            request=MagicMock(),
            response=resp,
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domain.analytics.clients.math_tool_client.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await _post_math_tool("/stats", {"bad": "payload"})

        # Only 1 attempt — HTTPStatusError is not retryable
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_connection_refused(self) -> None:
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _make_connection_refused()
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"ok": True}
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = AsyncMock()
        mock_client.post.side_effect = side_effect
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domain.analytics.clients.math_tool_client.httpx.AsyncClient", return_value=mock_client):
            result = await _post_math_tool("/stats", {"values": [1]})

        assert result["ok"] is True
        assert call_count == 3


# =========================================================================
# Public API wrappers
# =========================================================================

class TestPublicAPI:
    @pytest.mark.asyncio
    async def test_call_calculate_delegates(self) -> None:
        with patch(
            "domain.analytics.clients.math_tool_client._post_math_tool",
            new_callable=AsyncMock,
            return_value={"result": 42},
        ) as mock:
            result = await call_calculate({"expression": "6*7"})
        mock.assert_called_once_with("/calculate", {"expression": "6*7"})
        assert result == {"result": 42}

    @pytest.mark.asyncio
    async def test_call_stats_delegates(self) -> None:
        with patch(
            "domain.analytics.clients.math_tool_client._post_math_tool",
            new_callable=AsyncMock,
            return_value={"result": {"sum": 10}},
        ) as mock:
            result = await call_stats({"values": [1, 2, 3, 4], "operations": ["sum"]})
        mock.assert_called_once()
        assert result["result"]["sum"] == 10

    @pytest.mark.asyncio
    async def test_call_calculus_delegates(self) -> None:
        with patch(
            "domain.analytics.clients.math_tool_client._post_math_tool",
            new_callable=AsyncMock,
            return_value={"result": {"integral": 100}},
        ) as mock:
            result = await call_calculus({"operation": "integral", "points": []})
        mock.assert_called_once()
        assert result["result"]["integral"] == 100


# =========================================================================
# Timeout configuration
# =========================================================================

class TestTimeoutConfig:
    def test_connect_timeout_is_short(self) -> None:
        assert _TIMEOUT.connect == 5.0

    def test_read_timeout_is_from_settings(self) -> None:
        from domain.core.config import settings
        assert _TIMEOUT.read == float(settings.MATH_TOOL_TIMEOUT_SECONDS)

    def test_write_timeout_is_short(self) -> None:
        assert _TIMEOUT.write == 10.0

    def test_pool_timeout_is_short(self) -> None:
        assert _TIMEOUT.pool == 5.0

    def test_all_timeouts_are_finite(self) -> None:
        for name in ("connect", "read", "write", "pool"):
            val = getattr(_TIMEOUT, name)
            assert isinstance(val, (int, float)), f"{name} is not numeric: {val!r}"
            assert val > 0, f"{name} must be positive, got {val!r}"
