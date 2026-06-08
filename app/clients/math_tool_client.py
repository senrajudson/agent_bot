from typing import Any

import httpx

from app.core.config import settings


async def _post_math_tool(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = settings.MATH_TOOL_BASE_URL.rstrip("/")
    url = f"{base_url}{path}"

    async with httpx.AsyncClient(timeout=settings.MATH_TOOL_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def call_calculate(payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_math_tool("/calculate", payload)


async def call_stats(payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_math_tool("/stats", payload)


async def call_calculus(payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_math_tool("/calculus", payload)