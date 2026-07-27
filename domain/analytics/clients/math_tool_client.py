from __future__ import annotations

import logging
import socket
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from domain.core.config import get_domain_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry predicates
# ---------------------------------------------------------------------------

_RETRYABLE_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
    socket.gaierror,
    ConnectionError,
    OSError,
)


def _log_retry(retry_state: RetryCallState) -> None:
    """Log a warning when a retry is about to be attempted."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    attempt = retry_state.attempt_number
    logger.warning(
        "Math Tool connection attempt %d failed (%s: %s). Retrying...",
        attempt,
        type(exc).__name__,
        exc,
    )


# ---------------------------------------------------------------------------
# Internal POST helper
# ---------------------------------------------------------------------------

_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=float(get_domain_settings().MATH_TOOL_TIMEOUT_SECONDS),
    write=10.0,
    pool=5.0,
)


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    before_sleep=_log_retry,
    reraise=True,
)
async def _post_math_tool(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = get_domain_settings().MATH_TOOL_BASE_URL.rstrip("/")
    url = f"{base_url}{path}"

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        limits=httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
            keepalive_expiry=30,
        ),
    ) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_calculate(payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_math_tool("/calculate", payload)


async def call_stats(payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_math_tool("/stats", payload)


async def call_calculus(payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_math_tool("/calculus", payload)
