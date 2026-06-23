from __future__ import annotations

import logging
import socket
from typing import Any

import httpx

from domain.pims.clients.pi_web_api_client import buscar_dados_temporais_tag

logger = logging.getLogger(__name__)


def normalizar_numero(valor: Any) -> float | None:
    if isinstance(valor, bool):
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    if isinstance(valor, str):
        try:
            return float(valor.replace(",", ".").strip())
        except ValueError:
            return None

    return None


def _get_ci(data: dict[str, Any], key: str) -> Any:
    key_lower = key.lower()

    for data_key, value in data.items():
        if str(data_key).lower() == key_lower:
            return value

    return None


def extrair_raw_data(pi_response: dict[str, Any]) -> dict[str, Any]:
    if not pi_response:
        return {}

    raw_data = pi_response.get("raw_data")

    if isinstance(raw_data, dict):
        return raw_data

    content = pi_response.get("Content") or pi_response.get("content")

    if isinstance(content, dict):
        return content

    return pi_response


def extrair_point_metadata(pi_response: dict[str, Any]) -> dict[str, Any]:
    metadata = pi_response.get("point_metadata")
    return metadata if isinstance(metadata, dict) else {}


def extrair_items(pi_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_data = extrair_raw_data(pi_response)
    items = raw_data.get("Items") or raw_data.get("items") or []

    return items if isinstance(items, list) else []


def _extrair_valor_timestamp(item: dict[str, Any]) -> tuple[Any, Any]:
    value = _get_ci(item, "Value")
    timestamp = _get_ci(item, "Timestamp")

    if isinstance(value, dict):
        timestamp = _get_ci(value, "Timestamp") or timestamp
        value = _get_ci(value, "Value")

    return value, timestamp


def extrair_values(pi_response: dict[str, Any]) -> list[float]:
    values: list[float] = []

    for item in extrair_items(pi_response):
        value, _timestamp = _extrair_valor_timestamp(item)
        numero = normalizar_numero(value)

        if numero is not None:
            values.append(numero)

    return values


def extrair_points(pi_response: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    for item in extrair_items(pi_response):
        value, timestamp = _extrair_valor_timestamp(item)
        numero = normalizar_numero(value)

        if numero is None or not timestamp:
            continue

        points.append(
            {
                "timestamp": timestamp,
                "value": numero,
            }
        )

    return points


async def buscar_serie_pi(
    tag: str,
    start_time: str,
    end_time: str,
    interval: str | None = None,
    max_count: int = 200000,
    data_method: str | None = None,
    summary_type: str = "Average",
    summary_duration: str = "1h",
    calculation_basis: str = "TimeWeighted",
) -> dict[str, Any]:
    method = (data_method or "interpolated").strip().lower()

    if method == "interpolated" and not interval:
        interval = "1h"

    return await buscar_dados_temporais_tag(
        tag=tag,
        start_time=start_time,
        end_time=end_time,
        method=method,
        interval=interval,
        summary_type=summary_type,
        summary_duration=summary_duration,
        calculation_basis=calculation_basis,
        max_count=max_count,
    )