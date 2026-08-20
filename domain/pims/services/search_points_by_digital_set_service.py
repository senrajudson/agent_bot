from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from domain.pims.clients.pi_web_api_client import (
    search_points_by_digital_set as client_search,
)

logger = logging.getLogger(__name__)

_FORBIDDEN_CHAR_REGEX = re.compile(r"[*?\"\\\x00-\x1f\x7f-\x9f]")
_MAX_COUNT_CAP = 1000
_DEFAULT_MAX_COUNT = 100


def _get_digital_set_name(point: dict[str, Any]) -> str | None:
    """Extrai o nome do DigitalSet seguindo a ordem de precedência aprovada:

    1. DigitalSetName
    2. DigitalSet
    3. digitalset
    """
    for key in ("DigitalSetName", "DigitalSet", "digitalset"):
        val = point.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _build_error(
    digital_set_name: str,
    code: str,
    message: str,
    http_status: int | None = None,
    details: str | None = None,
) -> dict[str, Any]:
    err_body: dict[str, Any] = {
        "code": code,
        "message": message,
        "http_status": http_status,
        "details": details,
    }
    output_str = json.dumps(
        {
            "status": "error",
            "digital_set_name": digital_set_name,
            "error": err_body,
        },
        ensure_ascii=False,
    )
    return {
        "status": "error",
        "digital_set_name": digital_set_name,
        "error": err_body,
        "message": message,
        "output": output_str,
    }


async def search_pi_points_by_digital_set(
    digital_set_name: str,
    max_count: int = _DEFAULT_MAX_COUNT,
    start_index: int = 0,
) -> dict[str, Any]:
    """Busca PI Points digitais por conjunto digital (DigitalSet).

    Realiza validação estrita dos parâmetros de entrada, chamada read-only à
    PI Web API, filtragem defensiva local e cálculo de paginação pelos itens brutos.
    """
    name_clean = str(digital_set_name or "").strip()

    if not name_clean:
        return _build_error(
            digital_set_name=digital_set_name or "",
            code="invalid_digital_set_name",
            message="O nome do Digital Set não pode ser vazio ou conter apenas espaços.",
        )

    if _FORBIDDEN_CHAR_REGEX.search(name_clean):
        return _build_error(
            digital_set_name=name_clean,
            code="invalid_digital_set_name",
            message="O nome do Digital Set contém caracteres não permitidos (*, ?, \", \\ ou caracteres de controle).",
        )

    if not isinstance(max_count, int) or max_count < 1 or max_count > _MAX_COUNT_CAP:
        return _build_error(
            digital_set_name=name_clean,
            code="invalid_max_count",
            message=f"max_count deve ser um inteiro entre 1 e {_MAX_COUNT_CAP}.",
        )

    if not isinstance(start_index, int) or start_index < 0:
        return _build_error(
            digital_set_name=name_clean,
            code="invalid_start_index",
            message="start_index deve ser um inteiro maior ou igual a 0.",
        )

    try:
        raw_data = await client_search(
            digital_set_name=name_clean,
            max_count=max_count,
            start_index=start_index,
        )
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        logger.warning(
            "search_pi_points_by_digital_set HTTP %d: dset=%s",
            status_code,
            name_clean,
        )
        return _build_error(
            digital_set_name=name_clean,
            code="pi_web_api_query_unsupported" if status_code == 400 else "pi_web_api_request_failed",
            message=f"A PI Web API retornou erro HTTP {status_code}.",
            http_status=status_code,
        )
    except Exception as exc:
        logger.exception(
            "search_pi_points_by_digital_set error: dset=%s exc=%s",
            name_clean,
            exc,
        )
        return _build_error(
            digital_set_name=name_clean,
            code="pi_web_api_request_failed",
            message=f"Erro ao consultar a PI Web API: {exc}",
        )

    raw_items = raw_data.get("Items") or []
    raw_count = len(raw_items)
    requested_casefold = name_clean.casefold()

    filtered_items: list[dict[str, Any]] = []

    for point in raw_items:
        pt_type = str(point.get("PointType") or "").strip().casefold()
        if pt_type != "digital":
            continue

        resolved_dset = _get_digital_set_name(point)
        if not resolved_dset or resolved_dset.casefold() != requested_casefold:
            continue

        filtered_items.append(
            {
                "name": point.get("Name") or "",
                "description": point.get("Descriptor") or "",
                "point_type": point.get("PointType") or "Digital",
                "digital_set_name": resolved_dset,
                "path": point.get("Path") or "",
                "web_id": point.get("WebId") or "",
            }
        )

    returned_count = len(filtered_items)
    truncated = raw_count == max_count
    next_start_index = (start_index + raw_count) if truncated else None

    if returned_count == 0 and not truncated:
        status = "no_data"
        output_msg = f"Nenhum PI Point digital encontrado para o Digital Set '{name_clean}'."
    else:
        status = "success"
        output_msg = (
            f"Encontrados {returned_count} PI Point(s) digitais para o Digital Set '{name_clean}' "
            f"(índice {start_index} a {start_index + raw_count})."
        )

    result_payload = {
        "status": status,
        "digital_set_name": name_clean,
        "returned_count": returned_count,
        "start_index": start_index,
        "next_start_index": next_start_index,
        "truncated": truncated,
        "items": filtered_items,
        "message": output_msg,
        "output": json.dumps(
            {
                "status": status,
                "digital_set_name": name_clean,
                "returned_count": returned_count,
                "start_index": start_index,
                "next_start_index": next_start_index,
                "truncated": truncated,
                "items": filtered_items,
            },
            ensure_ascii=False,
        ),
    }

    return result_payload
