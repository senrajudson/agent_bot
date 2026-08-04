from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

SAFE_LOG_KEYS = frozenset({
    "url", "URL", "ip", "IP", "WebId", "webId",
    "Credential", "Authorization", "Password", "Secret",
    "PI_WEB_API_USERNAME", "PI_WEB_API_PASSWORD",
})


def safe_log_payload(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: (safe_log_payload(v) if isinstance(v, dict) else v)
            for k, v in data.items()
            if k not in SAFE_LOG_KEYS
        }
    if isinstance(data, (list, tuple)):
        return type(data)(safe_log_payload(item) for item in data)
    return data


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    EMPTY_RESULT = "EMPTY_RESULT"
    NOT_FOUND = "NOT_FOUND"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    AMBIGUOUS_RESOLUTION = "AMBIGUOUS_RESOLUTION"


@dataclass(frozen=True)
class PiPointResolution:
    status: ResolutionStatus
    tag: str
    items: tuple[dict[str, Any], ...] = ()
    transport_used: str | None = None
    http_status: int | None = None
    duration_ms: int = 0
    error_code: str | None = None
    error_message_safe: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.status == ResolutionStatus.RESOLVED


def _classify_http_error(exc: Exception, tag: str) -> ResolutionStatus:
    msg = str(exc)[:300].lower()
    if "401" in msg or "403" in msg or "407" in msg or "auth" in msg:
        return ResolutionStatus.AUTH_ERROR
    if "timeout" in msg or "connect" in msg:
        return ResolutionStatus.TRANSPORT_ERROR
    return ResolutionStatus.TRANSPORT_ERROR


def _classify_http_status(status: int, tag: str) -> ResolutionStatus:
    if status in (401, 403, 407):
        return ResolutionStatus.AUTH_ERROR
    if status == 404:
        return ResolutionStatus.NOT_FOUND
    return ResolutionStatus.TRANSPORT_ERROR


def _parse_batch_single_response(
    raw: dict[str, Any], tag: str
) -> PiPointResolution:
    point_entry = raw.get("point_0", {}) or {}
    status_code = point_entry.get("Status", 0)
    content = point_entry.get("Content") or {}

    if status_code != 200:
        resolution_status = _classify_http_status(status_code, tag)
        return PiPointResolution(
            status=resolution_status,
            tag=tag,
            http_status=status_code,
            transport_used="batch",
            error_code=resolution_status.value,
            error_message_safe=f"PI Web API retornou HTTP {status_code}",
        )

    if not content:
        return PiPointResolution(
            status=ResolutionStatus.EMPTY_RESULT,
            tag=tag,
            http_status=200,
            transport_used="batch",
        )

    items_raw = content.get("Items")
    if isinstance(items_raw, list) and items_raw:
        items = tuple(items_raw)
    elif isinstance(content, dict) and content.get("WebId"):
        items = (content,)
    else:
        return PiPointResolution(
            status=ResolutionStatus.INVALID_RESPONSE,
            tag=tag,
            http_status=200,
            transport_used="batch",
        )

    return PiPointResolution(
        status=ResolutionStatus.RESOLVED,
        tag=tag,
        items=items,
        http_status=200,
        transport_used="batch",
    )


async def resolve_pi_point(
    tag: str,
    *,
    batch_fn: Callable | None = None,
    get_fn: Callable | None = None,
) -> PiPointResolution:
    """Resolve PI Point por nome usando Batch como transporte primário.

    Args:
        tag: Nome da tag PI.
        batch_fn: Callable que executa POST /batch (default: execute_pi_batch).
        get_fn: Callable que executa GET /points (default: get_point_by_tag).
    """
    from domain.pims.clients.pi_web_api_client import (
        build_resolution_only_batch_request,
        execute_pi_batch,
        get_point_by_tag,
    )

    if batch_fn is None:
        batch_fn = execute_pi_batch
    if get_fn is None:
        get_fn = get_point_by_tag

    tag_limpa = str(tag or "").strip()
    if not tag_limpa:
        return PiPointResolution(
            status=ResolutionStatus.INVALID_RESPONSE,
            tag=tag or "",
            error_code="EMPTY_TAG",
            error_message_safe="Tag vazia ou inválida.",
        )

    t0 = time.monotonic()
    try:
        batch_request = build_resolution_only_batch_request(tag_limpa)
        raw = await batch_fn(batch_request)
        batch_ms = int((time.monotonic() - t0) * 1000)

        primary = _parse_batch_single_response(raw, tag_limpa)

        if primary.status == ResolutionStatus.RESOLVED:
            logger.info(
                "pi_point_resolved code=%s tag=%s transport=batch duration_ms=%d",
                primary.status.value,
                tag_limpa,
                batch_ms,
            )
            return PiPointResolution(
                status=primary.status,
                tag=primary.tag,
                items=primary.items,
                transport_used="batch",
                http_status=primary.http_status,
                duration_ms=batch_ms,
            )

        if primary.status not in (
            ResolutionStatus.EMPTY_RESULT,
            ResolutionStatus.INVALID_RESPONSE,
        ):
            logger.info(
                "pi_point_resolved code=%s tag=%s transport=batch duration_ms=%d",
                primary.status.value,
                tag_limpa,
                batch_ms,
            )
            return PiPointResolution(
                status=primary.status,
                tag=primary.tag,
                transport_used="batch",
                http_status=primary.http_status,
                duration_ms=batch_ms,
                error_code=primary.error_code,
                error_message_safe=primary.error_message_safe,
            )

        t1 = time.monotonic()
        try:
            fallback_raw = await get_fn(tag_limpa)
            fallback_ms = int((time.monotonic() - t1) * 1000)

            items_raw = fallback_raw.get("Items") if isinstance(fallback_raw, dict) else None
            if isinstance(items_raw, list) and items_raw:
                fallback_items = tuple(items_raw)
                fallback_status = ResolutionStatus.RESOLVED
            elif isinstance(fallback_raw, dict) and fallback_raw.get("WebId"):
                fallback_items = (fallback_raw,)
                fallback_status = ResolutionStatus.RESOLVED
            else:
                fallback_items = ()
                fallback_status = ResolutionStatus.EMPTY_RESULT

            if primary.status == ResolutionStatus.RESOLVED and fallback_status != ResolutionStatus.RESOLVED:
                resolved_status = ResolutionStatus.AMBIGUOUS_RESOLUTION
            elif primary.status != ResolutionStatus.RESOLVED and fallback_status == ResolutionStatus.RESOLVED:
                resolved_status = ResolutionStatus.RESOLVED
            elif primary.status != ResolutionStatus.RESOLVED and fallback_status != ResolutionStatus.RESOLVED:
                resolved_status = ResolutionStatus.EMPTY_RESULT
            else:
                resolved_status = ResolutionStatus.RESOLVED

            total_ms = batch_ms + fallback_ms
            logger.info(
                "pi_point_resolved code=%s tag=%s transport=fallback duration_ms=%d batch_status=%s fallback_status=%s",
                resolved_status.value,
                tag_limpa,
                total_ms,
                primary.status.value,
                fallback_status.value,
            )
            return PiPointResolution(
                status=resolved_status,
                tag=tag_limpa,
                items=fallback_items,
                transport_used="fallback",
                http_status=200,
                duration_ms=total_ms,
            )
        except Exception as fallback_exc:
            fallback_ms = int((time.monotonic() - t1) * 1000)
            total_ms = batch_ms + fallback_ms
            fallback_status = _classify_http_error(fallback_exc, tag_limpa)
            msg_safe = str(fallback_exc)[:200]
            logger.warning(
                "pi_point_resolved code=%s tag=%s transport=fallback duration_ms=%d error=%s",
                fallback_status.value,
                tag_limpa,
                total_ms,
                safe_log_payload({"error": msg_safe}),
            )
            return PiPointResolution(
                status=fallback_status,
                tag=tag_limpa,
                transport_used="fallback",
                duration_ms=total_ms,
                error_code=fallback_status.value,
                error_message_safe=msg_safe,
            )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        resolution_status = _classify_http_error(exc, tag_limpa)
        msg_safe = str(exc)[:200]
        logger.warning(
            "pi_point_resolved code=%s tag=%s transport=batch duration_ms=%d error=%s",
            resolution_status.value,
            tag_limpa,
            elapsed_ms,
            safe_log_payload({"error": msg_safe}),
        )
        return PiPointResolution(
            status=resolution_status,
            tag=tag_limpa,
            transport_used="batch",
            duration_ms=elapsed_ms,
            error_code=resolution_status.value,
            error_message_safe=msg_safe,
        )


def _build_multi_tag_batch(tags: list[str]) -> dict[str, Any]:
    """Monta batch com N sub-requests GET /points?path=... (uma por tag)."""
    from domain.pims.clients.pi_web_api_client import (
        POINT_SELECTED_FIELDS,
        _base_url,
        _pi_path,
    )

    batch_request: dict[str, Any] = {}
    base_url = _base_url()

    for index, tag in enumerate(tags):
        pi_path = _pi_path(tag)
        batch_request[f"point_{index}"] = {
            "Method": "GET",
            "Resource": (
                f"{base_url}/points"
                f"?path={pi_path}"
                f"&selectedFields={POINT_SELECTED_FIELDS}"
            ),
        }
    return batch_request


def _parse_multi_tag_batch_response(
    raw: dict[str, Any], tags: list[str]
) -> list[PiPointResolution]:
    """Parse batch response com N sub-respostas."""
    results: list[PiPointResolution] = []
    for i, tag in enumerate(tags):
        point_entry = raw.get(f"point_{i}", {}) or {}
        status_code = point_entry.get("Status", 0)
        content = point_entry.get("Content") or {}

        if status_code != 200:
            resolution_status = _classify_http_status(status_code, tag)
            results.append(PiPointResolution(
                status=resolution_status,
                tag=tag,
                http_status=status_code,
                transport_used="batch",
                error_code=resolution_status.value,
                error_message_safe=f"PI Web API retornou HTTP {status_code}",
            ))
            continue

        if not content:
            results.append(PiPointResolution(
                status=ResolutionStatus.EMPTY_RESULT,
                tag=tag,
                http_status=200,
                transport_used="batch",
            ))
            continue

        items_raw = content.get("Items")
        if isinstance(items_raw, list) and items_raw:
            items = tuple(items_raw)
        elif isinstance(content, dict) and content.get("WebId"):
            items = (content,)
        else:
            results.append(PiPointResolution(
                status=ResolutionStatus.INVALID_RESPONSE,
                tag=tag,
                http_status=200,
                transport_used="batch",
            ))
            continue

        results.append(PiPointResolution(
            status=ResolutionStatus.RESOLVED,
            tag=tag,
            items=items,
            http_status=200,
            transport_used="batch",
        ))
    return results


async def resolve_pi_points(
    tags: list[str],
    *,
    batch_fn: Callable | None = None,
    get_fn: Callable | None = None,
) -> list[PiPointResolution]:
    """Resolve múltiplos PI Points com um único POST /batch.

    Para cada tag com resultado EMPTY/INVALID, tenta fallback individual via GET.
    """
    from domain.pims.clients.pi_web_api_client import (
        execute_pi_batch,
        get_point_by_tag,
    )

    if batch_fn is None:
        batch_fn = execute_pi_batch
    if get_fn is None:
        get_fn = get_point_by_tag

    if not tags:
        return []

    clean_tags = [str(t or "").strip() for t in tags]
    empty_indices = [i for i, t in enumerate(clean_tags) if not t]
    for idx in empty_indices:
        clean_tags[idx] = f"__EMPTY_{idx}__"

    t0 = time.monotonic()
    try:
        batch_request = _build_multi_tag_batch(clean_tags)
        raw = await batch_fn(batch_request)
        batch_ms = int((time.monotonic() - t0) * 1000)

        results = _parse_multi_tag_batch_response(raw, clean_tags)

        need_fallback = [
            i for i, r in enumerate(results)
            if r.status in (ResolutionStatus.EMPTY_RESULT, ResolutionStatus.INVALID_RESPONSE)
        ]

        if need_fallback:
            fallback_tasks = []
            for idx in need_fallback:
                original_tag = tags[idx]
                fallback_tasks.append(_single_fallback(get_fn, original_tag, batch_ms))

            fallback_results = await asyncio.gather(*fallback_tasks)
            for i, idx in enumerate(need_fallback):
                results[idx] = fallback_results[i]

        logger.info(
            "pi_points_resolved count=%d resolved=%d duration_ms=%d",
            len(tags),
            sum(1 for r in results if r.status == ResolutionStatus.RESOLVED),
            batch_ms,
        )
        return results
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        resolution_status = _classify_http_error(exc, tags[0] if tags else "")
        msg_safe = str(exc)[:200]
        logger.warning(
            "pi_points_resolved code=%s count=%d duration_ms=%d error=%s",
            resolution_status.value,
            len(tags),
            elapsed_ms,
            safe_log_payload({"error": msg_safe}),
        )
        return [
            PiPointResolution(
                status=resolution_status,
                tag=t,
                transport_used="batch",
                duration_ms=elapsed_ms,
                error_code=resolution_status.value,
                error_message_safe=msg_safe,
            )
            for t in tags
        ]


async def _single_fallback(
    get_fn: Callable, tag: str, batch_ms: int
) -> PiPointResolution:
    """Fallback individual para uma tag."""
    t1 = time.monotonic()
    try:
        raw = await get_fn(tag)
        fallback_ms = int((time.monotonic() - t1) * 1000)
        total_ms = batch_ms + fallback_ms

        items_raw = raw.get("Items") if isinstance(raw, dict) else None
        if isinstance(items_raw, list) and items_raw:
            items = tuple(items_raw)
        elif isinstance(raw, dict) and raw.get("WebId"):
            items = (raw,)
        else:
            return PiPointResolution(
                status=ResolutionStatus.EMPTY_RESULT,
                tag=tag,
                transport_used="fallback",
                duration_ms=total_ms,
            )

        return PiPointResolution(
            status=ResolutionStatus.RESOLVED,
            tag=tag,
            items=items,
            transport_used="fallback",
            duration_ms=total_ms,
        )
    except Exception as exc:
        fallback_ms = int((time.monotonic() - t1) * 1000)
        total_ms = batch_ms + fallback_ms
        resolution_status = _classify_http_error(exc, tag)
        msg_safe = str(exc)[:200]
        return PiPointResolution(
            status=resolution_status,
            tag=tag,
            transport_used="fallback",
            duration_ms=total_ms,
            error_code=resolution_status.value,
            error_message_safe=msg_safe,
        )
