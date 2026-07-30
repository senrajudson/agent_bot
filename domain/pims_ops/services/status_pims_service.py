import json
import logging
import time
from typing import Any

logger = logging.getLogger("status_pims_service")

_ERR_NETWORK = "Falha de rede ao consultar /dataservers"
_ERR_INVALID_STATUS = "PI Web API retornou status inválido"
_ERR_UNEXPECTED = "PI Web API indisponível"

_LATENCY_THRESHOLD_MS = 200


def _classificar_latencia(available: bool, latency_ms: int) -> str:
    if not available:
        return "indisponivel"
    if latency_ms <= _LATENCY_THRESHOLD_MS:
        return "baixa"
    return "alta"


def _build_response(
    available: bool, latency_ms: int, error: str | None, latency_classification: str,
) -> str:
    return json.dumps(
        {
            "available": available,
            "latency_ms": latency_ms,
            "endpoint": "/dataservers",
            "error": error,
            "latency_classification": latency_classification,
        },
        ensure_ascii=False,
    )


async def consultar_health_pi_web_api_service() -> str:
    from domain.pims.clients.pi_web_api_client import get_dataservers

    start = time.perf_counter()
    try:
        raw = await get_dataservers()
        latency_ms = int((time.perf_counter() - start) * 1000)
    except Exception:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.warning("health check failed before response: %s", latency_ms)
        return _build_response(available=False, latency_ms=latency_ms, error=_ERR_UNEXPECTED, latency_classification=_classificar_latencia(False, latency_ms))

    status_code = raw.get("status_code")
    if status_code == 200 and raw.get("error") is None:
        logger.info("health check OK latency_ms=%d", latency_ms)
        return _build_response(available=True, latency_ms=latency_ms, error=None, latency_classification=_classificar_latencia(True, latency_ms))
    if status_code is None:
        logger.warning("health check network error latency_ms=%d", latency_ms)
        return _build_response(available=False, latency_ms=latency_ms, error=_ERR_NETWORK, latency_classification=_classificar_latencia(False, latency_ms))
    logger.warning("health check invalid status status_code=%s latency_ms=%d", status_code, latency_ms)
    return _build_response(available=False, latency_ms=latency_ms, error=_ERR_INVALID_STATUS, latency_classification=_classificar_latencia(False, latency_ms))
