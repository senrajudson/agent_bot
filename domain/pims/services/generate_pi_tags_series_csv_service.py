from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from domain.core.config import get_domain_settings
from domain.pims.clients.pi_web_api_client import (
    get_digital_set_states,
    get_interpolated_values_by_tag,
    get_point_by_tag,
    get_recorded_values_by_tag,
)
from domain.pims.utils.digital_states import resolve_digital_set_name
from domain.shared.errors import DomainValidationError, ValidationErrorCode
from domain.shared.time.pi_time_resolver import DEFAULT_PI_TIMEZONE, resolve_pi_time_range

logger = logging.getLogger(__name__)

MAX_ERROR_MESSAGE_CHARS = 512

_INTERVAL_REGEX = re.compile(r"^[1-9][0-9]*(s|m|h|d)$")
_INTERVAL_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

MAX_TAGS = 10
MAX_DAYS = 31
MAX_ESTIMATED_ROWS = 1_000_000
MAX_COUNT_RECORDED = 150_000
SEMAPHORE_LIMIT = 5

# Fuso horário de saída para a coluna Timestamp do CSV.
# Reutiliza DEFAULT_PI_TIMEZONE de domain.shared.time.pi_time_resolver.
_SP_TZ: ZoneInfo = ZoneInfo(DEFAULT_PI_TIMEZONE)

_CSV_SCHEMA = (
    ("Tag", "tag"),
    ("Timestamp", "timestamp"),
    ("Value", "value"),
    ("EngineeringUnits", "eng_unit"),
    ("Good", "good"),
    ("Questionable", "questionable"),
    ("Substituted", "substituted"),
    ("Annotated", "annotated"),
    ("Error", "error"),
    ("ValueType", "value_type"),
    ("DigitalStateCode", "digital_state_code"),
    ("DigitalStateName", "digital_state_name"),
)
_CSV_COLUMNS = [header for header, _ in _CSV_SCHEMA]


def _row_to_csv_values(row: dict[str, Any]) -> list[Any]:
    return [row[field] for _, field in _CSV_SCHEMA]


def _warning(code: str, tag: str, message: str) -> dict[str, str]:
    return {"code": code, "tag": tag, "message": message}


def _warning_with_key(code: str, tag: str, key_extra: str, message: str) -> dict[str, str]:
    return {"code": code, "tag": tag, "key": f"{tag}:{key_extra}", "message": message}


def _deduplicate_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in warnings:
        code = item.get("code", "")
        key = item.get("key") or item.get("tag", "")
        dedup_key = (code, key)
        if dedup_key not in seen:
            seen.add(dedup_key)
            result.append(item)
    return result


def _normalize_digital_state_key(key: Any) -> int | str | None:
    if key is None:
        return None
    if isinstance(key, int):
        return key
    if isinstance(key, float):
        if key == int(key):
            return int(key)
        return key
    if isinstance(key, str):
        try:
            if "." in key:
                f = float(key)
                if f == int(f):
                    return int(f)
                return f
            return int(key)
        except ValueError:
            return key
    return key


def _build_state_map(
    digital_states: list[dict[str, Any]],
) -> dict[int | str, dict[str, Any]]:
    state_map: dict[int | str, dict[str, Any]] = {}
    for state in digital_states:
        code_raw = state.get("indice")
        if code_raw is None:
            code_raw = state.get("Value")
        if code_raw is None:
            code_raw = state.get("code")
        if code_raw is None:
            continue
        code = _normalize_digital_state_key(code_raw)
        if code is None:
            continue
        state_map[code] = {
            "name": state.get("nome") or state.get("Name") or "",
            "description": state.get("descricao") or state.get("Description") or "",
        }
    return state_map


def _extract_digital_value(
    raw_value: Any,
    point_type: str,
) -> tuple[Any, str | None]:
    if point_type == "digital":
        if isinstance(raw_value, dict):
            return raw_value.get("Value"), raw_value.get("Name")
        return raw_value, None
    if isinstance(raw_value, dict):
        return raw_value.get("Value"), raw_value.get("Name")
    return raw_value, None


def _resolve_digital_state_name(
    code: Any,
    state_map: dict[int | str, dict[str, Any]],
    upstream_name: str | None,
) -> tuple[str, str | None]:
    normalized = _normalize_digital_state_key(code)
    if normalized is not None and normalized in state_map:
        return state_map[normalized]["name"], None
    if upstream_name:
        return upstream_name, "UNKNOWN_DIGITAL_STATE"
    return "", "UNKNOWN_DIGITAL_STATE"


async def _fetch_point_metadata_batch(
    tags: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for tag in tags:
        try:
            point_data = await get_point_by_tag(tag)
            result[tag] = point_data
        except Exception:
            result[tag] = {}
    return result


def _interval_to_seconds(interval: str) -> int:
    m = _INTERVAL_REGEX.match(interval)
    if not m:
        raise DomainValidationError(
            ValidationErrorCode.INVALID_INTERVAL,
            f"Intervalo inválido: '{interval}'. Use formato como 1s, 1m, 5m, 1h, 1d.",
        )
    num = int(interval[:-1])
    unit = interval[-1]
    return num * _INTERVAL_SECONDS[unit]


def validate_series_csv_contract(
    tags: list[str],
    start_time: str,
    end_time: str,
    data_method: str,
    interval: str | None,
) -> tuple[list[str], str, str, str, str | None, int]:
    cleaned_tags: list[str] = []
    seen: set[str] = set()
    for t in tags:
        t_stripped = t.strip()
        if not t_stripped:
            raise DomainValidationError(
                ValidationErrorCode.INVALID_ARGUMENT_COMBINATION,
                "Tag vazia não é permitida.",
            )
        if t_stripped not in seen:
            seen.add(t_stripped)
            cleaned_tags.append(t_stripped)

    if not cleaned_tags:
        raise DomainValidationError(
            ValidationErrorCode.INVALID_ARGUMENT_COMBINATION,
            "Pelo menos uma tag deve ser informada.",
        )
    if len(cleaned_tags) > MAX_TAGS:
        raise DomainValidationError(
            ValidationErrorCode.INVALID_ARGUMENT_COMBINATION,
            f"Máximo de {MAX_TAGS} tags por requisição.",
        )

    norm_method = data_method.strip().lower()
    if norm_method not in ("interpolated", "recorded"):
        raise DomainValidationError(
            ValidationErrorCode.INVALID_DATA_METHOD,
            f"data_method inválido: '{data_method}'. Use 'interpolated' ou 'recorded'.",
        )

    if norm_method == "interpolated":
        if interval is not None:
            _interval_to_seconds(interval)
            resolved_interval = interval
        else:
            resolved_interval = "1m"
    else:
        if interval is not None:
            raise DomainValidationError(
                ValidationErrorCode.INTERVAL_NOT_ALLOWED,
                "interval não é permitido para data_method='recorded'.",
            )
        resolved_interval = None

    resolved = resolve_pi_time_range(start_time, end_time)

    window_seconds = resolved.window_seconds
    max_window_seconds = MAX_DAYS * 86400
    if window_seconds > max_window_seconds:
        raise DomainValidationError(
            ValidationErrorCode.INVALID_TIME_WINDOW,
            f"Período máximo de {MAX_DAYS} dias excedido ({window_seconds / 86400:.1f} dias).",
        )

    estimated_rows = 0
    if norm_method == "interpolated" and resolved_interval:
        interval_s = _interval_to_seconds(resolved_interval)
        estimated_intervals = math.ceil(window_seconds / interval_s) if interval_s > 0 else 0
        estimated_rows = len(cleaned_tags) * estimated_intervals
        if estimated_rows > MAX_ESTIMATED_ROWS:
            raise DomainValidationError(
                ValidationErrorCode.ESTIMATED_ROW_LIMIT_EXCEEDED,
                f"Estimativa de {estimated_rows} linhas excede o limite de {MAX_ESTIMATED_ROWS}. "
                f"Reduza o número de tags, o período ou aumente o interval.",
            )

    return (
        cleaned_tags,
        resolved.start_iso,
        resolved.end_iso,
        norm_method,
        resolved_interval,
        estimated_rows,
    )


def _extract_timestamp(ts_raw: Any) -> str | None:
    """Converte timestamp da PI Web API (UTC) para America/Sao_Paulo.

    Preserva o instante absoluto e emite ISO 8601 com offset explícito.
    Fuso horário de saída: DEFAULT_PI_TIMEZONE (domain.shared.time.pi_time_resolver).
    Entrada naive (sem tzinfo) é tratada como UTC.
    """
    if not ts_raw:
        return None
    try:
        dt = datetime.fromisoformat(str(ts_raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_SP_TZ).isoformat()
    except Exception:
        return None


def _normalize_quality(point: dict[str, Any]) -> dict[str, Any]:
    is_good = point.get("Good")
    is_questionable = point.get("Questionable", False)
    is_substituted = point.get("Substituted", False)
    is_annotated = point.get("Annotated", False)
    errors = point.get("Errors") or point.get("Error") or ""
    value = point.get("Value")
    if is_good is False:
        value = None
    return {
        "value": value,
        "good": bool(is_good) if is_good is not None else True,
        "questionable": bool(is_questionable),
        "substituted": bool(is_substituted),
        "annotated": bool(is_annotated),
        "error": str(errors)[:512] if errors else "",
    }


def _extract_point_type(point_meta: dict[str, Any]) -> str:
    return str(point_meta.get("PointType") or "").strip().lower()


def _get_point_metadata(pi_response: dict[str, Any]) -> dict[str, Any]:
    items = pi_response.get("Items") or []
    return items[0] if items else {}


async def _acquire_tag_data_interpolated(
    tag: str,
    start_time: str,
    end_time: str,
    interval: str,
    sem: asyncio.Semaphore,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    async with sem:
        try:
            pi_response = await get_interpolated_values_by_tag(
                tag=tag,
                start_time=start_time,
                end_time=end_time,
                interval=interval,
            )
        except Exception as exc:
            logger.warning("Failed to acquire interpolated data for tag %s: %s", tag, exc)
            return tag, [], {"error": str(exc)[:MAX_ERROR_MESSAGE_CHARS]}

    point_meta = _get_point_metadata(pi_response)
    point_type = _extract_point_type(point_meta)
    if point_type == "string":
        logger.warning("String point type not supported for interpolated: %s", tag)
        return tag, [], {"error": "String point type não suportado para interpolated"}

    raw_items = pi_response.get("Items") or []
    metadata: dict[str, Any] = {}
    if not raw_items:
        metadata["warnings"] = [_warning(
            "TAG_NO_DATA",
            tag,
            "Nenhum dado encontrado para a tag na janela solicitada.",
        )]
    rows: list[dict[str, Any]] = []
    eng_unit = str(point_meta.get("EngineeringUnits") or "")
    for item in raw_items:
        ts = _extract_timestamp(item.get("Timestamp"))
        if ts is None:
            continue
        quality = _normalize_quality(item)
        raw_value = item.get("Value")
        digital_state_code = None
        digital_state_name = None
        value_type = "numeric"
        if isinstance(raw_value, dict):
            digital_state_code = raw_value.get("Value")
            digital_state_name = raw_value.get("Name")
            value_type = "digital"
        rows.append({
            "tag": tag,
            "timestamp": ts,
            "value": quality["value"],
            "eng_unit": eng_unit,
            "good": quality["good"],
            "questionable": quality["questionable"],
            "substituted": quality["substituted"],
            "annotated": quality["annotated"],
            "error": quality["error"],
            "value_type": value_type,
            "digital_state_code": digital_state_code,
            "digital_state_name": digital_state_name,
        })
    return tag, rows, metadata


async def _acquire_tag_data_recorded(
    tag: str,
    start_time: str,
    end_time: str,
    sem: asyncio.Semaphore,
    *,
    requested_max_count: int = MAX_COUNT_RECORDED,
    pre_resolved_metadata: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    async with sem:
        try:
            pi_response = await get_recorded_values_by_tag(
                tag=tag,
                start_time=start_time,
                end_time=end_time,
                max_count=requested_max_count,
            )
        except Exception as exc:
            logger.warning("Failed to acquire recorded data for tag %s: %s", tag, exc)
            return tag, [], {"error": str(exc)[:MAX_ERROR_MESSAGE_CHARS]}

    point_meta = _get_point_metadata(pi_response)
    raw_items = pi_response.get("Items") or []
    metadata: dict[str, Any] = {}
    warnings: list[dict[str, str]] = []
    if not raw_items:
        warnings.append(_warning(
            "TAG_NO_DATA",
            tag,
            "Nenhum dado encontrado para a tag na janela solicitada.",
        ))
    if len(raw_items) >= requested_max_count:
        warnings.append(_warning(
            "POSSIBLE_RECORDED_TRUNCATION",
            tag,
            "A tag atingiu o limite máximo de pontos Recorded retornáveis nesta consulta. "
            "O conjunto pode estar truncado.",
        ))

    effective_meta = pre_resolved_metadata or point_meta
    point_type = _extract_point_type(effective_meta)
    if not point_type:
        point_type = _extract_point_type(point_meta)
    is_digital = point_type == "digital"

    state_map: dict[int | str, dict[str, Any]] = {}
    if is_digital and raw_items:
        ds_resolution = resolve_digital_set_name(
            point_data=effective_meta,
            digitalset_attribute=None,
        )
        ds_name = ds_resolution.name
        if ds_name:
            try:
                ds_result = await get_digital_set_states(ds_name)
                raw_states = ds_result.get("states") or ds_result.get("Items") or []
                state_map = _build_state_map(raw_states)
            except Exception as exc:
                logger.warning(
                    "Failed to resolve digital set states for tag %s: %s", tag, exc
                )
                warnings.append(_warning(
                    "DIGITAL_STATE_RESOLUTION_FAILED",
                    tag,
                    "Não foi possível resolver os estados do Digital Set. "
                    "DigitalStateName pode estar incompleto.",
                ))
        else:
            warnings.append(_warning(
                "DIGITAL_STATE_RESOLUTION_FAILED",
                tag,
                "Nome do Digital Set não encontrado na metadata da tag.",
            ))

    if warnings:
        metadata["warnings"] = warnings
    rows: list[dict[str, Any]] = []
    eng_unit = str(point_meta.get("EngineeringUnits") or "")
    seen_unknown: set[int | str] = set()
    for item in raw_items:
        ts = _extract_timestamp(item.get("Timestamp"))
        if ts is None:
            continue
        quality = _normalize_quality(item)
        raw_value = item.get("Value")
        if is_digital:
            code_raw, upstream_name = _extract_digital_value(raw_value, "digital")
            if code_raw is not None:
                code_key = _normalize_digital_state_key(code_raw)
                resolved_name, unknown_warning = _resolve_digital_state_name(
                    code_raw, state_map, upstream_name
                )
                if unknown_warning and code_key is not None and code_key not in seen_unknown:
                    seen_unknown.add(code_key)
                    warnings.append(_warning_with_key(
                        "UNKNOWN_DIGITAL_STATE",
                        tag,
                        str(code_raw),
                        f"Código digital '{code_raw}' não encontrado no Digital Set atual.",
                    ))
                    if "warnings" not in metadata:
                        metadata["warnings"] = warnings
                digital_state_code = code_raw
                digital_state_name = resolved_name
            else:
                digital_state_code = None
                digital_state_name = None
            value_type = "digital"
        else:
            digital_state_code = None
            digital_state_name = None
            value_type = "numeric"
            if isinstance(raw_value, dict):
                digital_state_code = raw_value.get("Value")
                digital_state_name = raw_value.get("Name")
                value_type = "digital"
        rows.append({
            "tag": tag,
            "timestamp": ts,
            "value": quality["value"],
            "eng_unit": eng_unit,
            "good": quality["good"],
            "questionable": quality["questionable"],
            "substituted": quality["substituted"],
            "annotated": quality["annotated"],
            "error": quality["error"],
            "value_type": value_type,
            "digital_state_code": digital_state_code,
            "digital_state_name": digital_state_name,
        })
    return tag, rows, metadata


async def generate_pi_tags_series_csv_service(
    tags: list[str],
    start_time: str,
    end_time: str = "*",
    data_method: str = "interpolated",
    interval: str | None = None,
    *,
    recorded_max_count: int = MAX_COUNT_RECORDED,
) -> dict[str, Any]:
    (cleaned_tags, start_iso, end_iso, norm_method, resolved_interval, estimated_rows) = (
        validate_series_csv_contract(tags, start_time, end_time, data_method, interval)
    )

    point_metadata_map: dict[str, dict[str, Any]] = {}
    if norm_method == "recorded":
        point_metadata_map = await _fetch_point_metadata_batch(cleaned_tags)

    sem = asyncio.Semaphore(SEMAPHORE_LIMIT)
    tasks = []
    for tag in cleaned_tags:
        if norm_method == "interpolated":
            tasks.append(
                _acquire_tag_data_interpolated(
                    tag, start_iso, end_iso, resolved_interval, sem
                )
            )
        else:
            pre_meta = point_metadata_map.get(tag) or {}
            tasks.append(
                _acquire_tag_data_recorded(
                    tag, start_iso, end_iso, sem,
                    requested_max_count=recorded_max_count,
                    pre_resolved_metadata=pre_meta,
                )
            )

    results = await asyncio.gather(*tasks)
    all_rows: list[dict[str, Any]] = []
    errors_summary: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    tag_no_data_count = 0
    tag_ok_count = 0

    for tag, tag_rows, tag_error in results:
        if tag_error:
            warnings.extend(tag_error.get("warnings", []))
            if "error" in tag_error:
                errors_summary.append({
                    "tag": tag,
                    "error": tag_error.get("error", "Erro desconhecido"),
                })
                continue
        if not tag_rows:
            tag_no_data_count += 1
            continue
        tag_ok_count += 1
        all_rows.extend(tag_rows)

    warnings = _deduplicate_warnings(warnings)

    if not all_rows and not errors_summary:
        return {
            "status": "no_data",
            "warnings": warnings,
            "tool_result": {
                "tags_requested": len(cleaned_tags),
                "tags_processed": 0,
                "tags_no_data": tag_no_data_count,
                "tags_failed": len(errors_summary),
                "start_time": start_iso,
                "end_time": end_iso,
                "data_method": norm_method,
                "interval": resolved_interval,
                "row_count": 0,
            },
        }

    if errors_summary and not all_rows:
        return {
            "status": "all_failed",
            "warnings": warnings,
            "errors_summary": errors_summary,
            "tool_result": {
                "tags_requested": len(cleaned_tags),
                "tags_processed": 0,
                "tags_failed": len(errors_summary),
            },
        }

    all_rows.sort(key=lambda r: (r["timestamp"], cleaned_tags.index(r["tag"])))

    status = "partial_success" if errors_summary or tag_no_data_count else "success"

    return {
        "status": status,
        "rows": all_rows,
        "tool_result": {
            "tags_requested": len(cleaned_tags),
            "tags_processed": tag_ok_count,
            "tags_no_data": tag_no_data_count,
            "tags_failed": len(errors_summary),
            "start_time": start_iso,
            "end_time": end_iso,
            "data_method": norm_method,
            "interval": resolved_interval,
            "estimated_rows": estimated_rows,
            "actual_rows": len(all_rows),
        },
        "errors_summary": errors_summary,
        "warnings": warnings,
        "column_headers": _CSV_COLUMNS,
    }
