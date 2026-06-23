"""Non-blocking startup health checks for external dependencies."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def check_math_tool(base_url: str, timeout: float = 3.0) -> None:
    """Probe the Math Tool service and log a warning if unreachable.

    This is intentionally non-blocking: a failure does NOT prevent the
    MCP server from starting.
    """
    url = f"{base_url.rstrip('/')}/"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            # Any HTTP response (even 404) means the service is alive.
            logger.info(
                "Math Tool health check OK — %s responded with HTTP %d",
                base_url,
                response.status_code,
            )
    except Exception as exc:
        logger.warning(
            "Math Tool health check FAILED — %s is unreachable (%s: %s). "
            "Calls to Math Tool will be retried automatically.",
            base_url,
            type(exc).__name__,
            exc,
        )
