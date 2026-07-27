from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from domain.core.config import get_domain_settings


def _datetime_to_loki_ns(value: datetime) -> str:
    return str(int(value.timestamp() * 1_000_000_000))


def _build_auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {}

    if get_domain_settings().GRAFANA_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {get_domain_settings().GRAFANA_BEARER_TOKEN}"

    return headers


async def query_loki_range(
    query: str,
    lookback_minutes: int,
    limit: int,
) -> dict[str, Any]:
    if not get_domain_settings().GRAFANA_LOKI_QUERY_RANGE_URL:
        raise ValueError("GRAFANA_LOKI_QUERY_RANGE_URL não configurada no .env.")

    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=lookback_minutes)

    params = {
        "query": query,
        "start": _datetime_to_loki_ns(start),
        "end": _datetime_to_loki_ns(now),
        "limit": str(limit),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            get_domain_settings().GRAFANA_LOKI_QUERY_RANGE_URL,
            params=params,
            headers=_build_auth_headers(),
        )

    response.raise_for_status()
    return response.json()