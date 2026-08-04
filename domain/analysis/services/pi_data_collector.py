from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from domain.analysis.models import AnalysisError, AnalysisPoint, TagMetadata, ZeroPolicy
from domain.pims.clients.pi_web_api_client import (
    get_digital_set_states,
    get_interpolated_values_by_tag,
    get_point_by_tag,
    get_recorded_values_by_tag,
)

logger = logging.getLogger(__name__)

INVALID_DIGITAL_SETS = frozenset({
    "n/a", "nao cadastrado", "nao se aplica",
    "sem digital set", "null", "undefined", "",
})


@dataclass(frozen=True)
class CollectedData:
    metadata: TagMetadata
    recorded: list[AnalysisPoint] = field(default_factory=list)
    interpolated: list[AnalysisPoint] = field(default_factory=list)
    digital_initial: str | None = None
    digital_states: list[dict] = field(default_factory=list)


_STATUS_TO_ERROR_CODE = {
    "RESOLVED": None,
    "EMPTY_RESULT": "EMPTY_RESULT",
    "NOT_FOUND": "TAG_NOT_FOUND",
    "INVALID_RESPONSE": "INVALID_RESPONSE",
    "TRANSPORT_ERROR": "PI_TRANSPORT_ERROR",
    "AUTH_ERROR": "PI_AUTH_ERROR",
    "AMBIGUOUS_RESOLUTION": "AMBIGUOUS_RESOLUTION",
}


class PiDataCollector:
    def __init__(
        self,
        *,
        max_concurrency: int = 5,
        resolver: Callable | None = None,
    ) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self._resolver = resolver

    async def fetch_one(
        self, tag: str, start: str, end: str
    ) -> CollectedData | AnalysisError:
        try:
            if self._resolver is not None:
                resolution = await self._resolver(tag)
                status_val = resolution.status.value
                error_code = _STATUS_TO_ERROR_CODE.get(status_val)

                if error_code is not None:
                    retryable = status_val in ("TRANSPORT_ERROR", "EMPTY_RESULT", "AMBIGUOUS_RESOLUTION")
                    return AnalysisError(
                        tag=tag,
                        code=error_code,
                        message=resolution.error_message_safe or f"Resolução retornou status: {status_val}",
                        retryable=retryable,
                    )

                if not resolution.items:
                    return AnalysisError(
                        tag=tag,
                        code="TAG_NOT_FOUND",
                        message=f"Tag não encontrada: {tag}",
                        retryable=False,
                    )

                item = resolution.items[0]
            else:
                metadata_raw = await get_point_by_tag(tag)
                if not metadata_raw or not metadata_raw.get("Items"):
                    return AnalysisError(
                        tag=tag,
                        code="TAG_NOT_FOUND",
                        message=f"Tag não encontrada: {tag}",
                        retryable=False,
                    )
                item = metadata_raw["Items"][0] if isinstance(metadata_raw.get("Items"), list) else metadata_raw

            metadata = self._build_metadata(tag, item)

            if metadata.point_type == "digital":
                return await self._fetch_digital(tag, start, end, metadata)

            recorded, interpolated = await asyncio.gather(
                self._fetch_recorded(tag, start, end),
                self._fetch_interpolated(tag, start, end),
            )
            return CollectedData(
                metadata=metadata,
                recorded=recorded,
                interpolated=interpolated,
            )

        except Exception as exc:
            msg = str(exc)[:300]
            if "401" in msg or "auth" in msg.lower():
                return AnalysisError(tag=tag, code="PI_AUTH_ERROR", message=msg, retryable=False)
            if "timeout" in msg.lower() or "connect" in msg.lower():
                return AnalysisError(tag=tag, code="PI_TIMEOUT", message=msg, retryable=True)
            return AnalysisError(tag=tag, code="PI_RESPONSE_INVALID", message=msg, retryable=False)

    async def fetch_many(
        self, tags: list[str], start: str, end: str
    ) -> dict[str, CollectedData | AnalysisError]:
        async def _bounded(t: str) -> tuple[str, CollectedData | AnalysisError]:
            async with self._sem:
                result = await self.fetch_one(t, start, end)
                return t, result

        results = await asyncio.gather(*[_bounded(t) for t in tags])
        return {t: r for t, r in results}

    async def _fetch_recorded(
        self, tag: str, start: str, end: str
    ) -> list[AnalysisPoint]:
        try:
            raw = await get_recorded_values_by_tag(tag, start, end)
            return self._parse_points(raw)
        except Exception as exc:
            logger.warning("Recorded fetch failed for %s: %s", tag, exc)
            return []

    async def _fetch_interpolated(
        self, tag: str, start: str, end: str
    ) -> list[AnalysisPoint]:
        try:
            raw = await get_interpolated_values_by_tag(tag, start, end, "5m")
            return self._parse_points(raw)
        except Exception as exc:
            logger.warning("Interpolated fetch failed for %s: %s", tag, exc)
            return []

    async def _fetch_digital(
        self, tag: str, start: str, end: str, metadata: TagMetadata
    ) -> CollectedData | AnalysisError:
        ds = metadata.digital_set or ""
        ds_lower = ds.strip().lower()
        if not ds or ds_lower in INVALID_DIGITAL_SETS or ds_lower in ("null", "undefined", ""):
            return AnalysisError(
                tag=tag,
                code="INVALID_DIGITAL_SET",
                message=f"DigitalSet inválido ou ausente para tag digital: {tag}",
                retryable=False,
            )

        try:
            digital_set_result = await get_digital_set_states(ds)
            digital_states = digital_set_result.get("states", [])
        except Exception as exc:
            return AnalysisError(
                tag=tag,
                code="PI_RESPONSE_INVALID",
                message=f"Erro ao obter digital states: {str(exc)[:200]}",
                retryable=False,
            )

        recorded = await self._fetch_recorded(tag, start, end)

        initial_state: str | None = None
        if recorded:
            first_val = recorded[0].value
            if first_val is not None:
                idx = int(first_val)
                for s in digital_states:
                    if s.get("indice") == idx:
                        initial_state = s.get("nome")
                        break

        return CollectedData(
            metadata=metadata,
            recorded=recorded,
            digital_initial=initial_state,
            digital_states=digital_states,
        )

    def _build_metadata(self, tag: str, item: dict[str, Any]) -> TagMetadata:
        point_type_raw = str(item.get("PointType", "")).lower()
        if point_type_raw == "digital":
            point_type = "digital"
        else:
            point_type = "numeric"

        digital_set = item.get("DigitalSet")
        if digital_set and str(digital_set).strip().lower() in INVALID_DIGITAL_SETS:
            digital_set = None

        return TagMetadata(
            tag=tag,
            point_type=point_type,  # type: ignore[arg-type]
            descriptor=str(item.get("Descriptor", "")),
            engineering_units=item.get("EngineeringUnits"),
            digital_set=digital_set,
        )

    def _parse_points(self, raw: dict[str, Any]) -> list[AnalysisPoint]:
        items = raw.get("Items") or raw.get("items") or []
        if not isinstance(items, list):
            return []

        points: list[AnalysisPoint] = []
        for item in items:
            ts = item.get("Timestamp")
            val = item.get("Value")
            if ts is None:
                continue
            value: float | None = None
            if isinstance(val, dict):
                value = val.get("Value")
            elif isinstance(val, (int, float)):
                value = float(val)
            elif isinstance(val, str):
                try:
                    value = float(val.replace(",", "."))
                except (ValueError, TypeError):
                    value = None

            good = item.get("Good", True)
            questionable = item.get("Questionable", False)
            substituted = item.get("Substituted", False)

            points.append(
                AnalysisPoint(
                    timestamp=str(ts),
                    value=value,
                    good=bool(good) if good is not None else True,
                    questionable=bool(questionable) if questionable is not None else False,
                    substituted=bool(substituted) if substituted is not None else False,
                )
            )
        return points
