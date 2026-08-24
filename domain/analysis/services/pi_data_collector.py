from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from domain.analysis.models import (
    AnalysisCompleteness,
    AnalysisCompletenessMetadata,
    AnalysisError,
    AnalysisPoint,
    BucketSummaryResult,
    LimitStatus,
    TagMetadata,
    ZeroPolicy,
)
from domain.analysis.services.limit_resolver import resolve_effective_point_limit
from domain.analysis.services.pi_summary_response_mapper import PiSummaryResponseMapper
from domain.pims.clients.pi_web_api_client import (
    get_digital_set_states,
    get_interpolated_values_by_tag,
    get_point_by_tag,
    get_recorded_values_by_tag,
    get_streamsets_summary,
    get_value_at_or_before_by_web_id,
)

SUMMARY_BATCH_SIZE = 25

from domain.pims.utils.digital_states import (
    DigitalSetSource,
    INVALID_DIGITAL_SETS,
    resolve_digital_set_name,
)

logger = logging.getLogger(__name__)


def get_event_identity(p: AnalysisPoint) -> tuple:
    """T016: Retorna a tupla de identidade completa de um evento PI."""
    return (
        p.timestamp,
        p.value,
        p.good,
        getattr(p, "questionable", False),
        getattr(p, "substituted", False),
        getattr(p, "annotated", False),
    )


@dataclass(frozen=True)
class CollectedData:
    metadata: TagMetadata
    recorded: list[AnalysisPoint] = field(default_factory=list)
    interpolated: list[AnalysisPoint] = field(default_factory=list)
    digital_initial: str | None = None
    digital_states: list[dict] = field(default_factory=list)
    digital_seed: AnalysisPoint | None = None
    completeness: AnalysisCompletenessMetadata | None = None
    first_excluded_point: AnalysisPoint | None = None
    bucket_summaries: list[BucketSummaryResult] = field(default_factory=list)



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
        recorded_max_count: int = 150_000,
        max_concurrency: int = 5,
        resolver: Callable | None = None,
    ) -> None:
        self._sem = asyncio.Semaphore(max_concurrency)
        self._resolver = resolver
        self._recorded_max_count = recorded_max_count

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
                return await self._fetch_digital(tag, start, end, metadata, item)

            (recorded, completeness, first_excluded), interpolated = await asyncio.gather(
                self._fetch_recorded_with_probe(tag, start, end),
                self._fetch_interpolated(tag, start, end),
            )
            return CollectedData(
                metadata=metadata,
                recorded=recorded,
                interpolated=interpolated,
                completeness=completeness,
                first_excluded_point=first_excluded,
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

    async def _fetch_recorded_with_probe(
        self, tag: str, start: str, end: str
    ) -> tuple[list[AnalysisPoint], AnalysisCompletenessMetadata, AnalysisPoint | None]:
        resolution = resolve_effective_point_limit(configured_limit=self._recorded_max_count)
        limit = resolution.effective_limit

        try:
            raw = await get_recorded_values_by_tag(tag, start, end, max_count=limit)
            points = self._parse_points(raw)
        except Exception as exc:
            logger.warning("Recorded fetch failed for %s: %s", tag, exc)
            points = []

        count = len(points)
        effective_start = start
        effective_end = end
        first_excluded: AnalysisPoint | None = None
        probe_performed = False

        if count < limit:
            status = LimitStatus.NOT_REACHED
            completeness = AnalysisCompleteness.COMPLETE
            truncated = False
            effective_end = end
        else:
            # count == limit: executar probe de 1 chamada
            probe_performed = True
            try:
                last_point = points[-1]
                effective_end = last_point.timestamp
                last_identity = get_event_identity(last_point)

                # Busca max 2 pontos a partir do timestamp do último evento
                probe_raw = await get_recorded_values_by_tag(tag, last_point.timestamp, end, max_count=2)
                probe_points = self._parse_points(probe_raw)

                # Filtrar duplicatas pela identidade completa de evento
                distinct_probe = [p for p in probe_points if get_event_identity(p) != last_identity]

                if not distinct_probe:
                    status = LimitStatus.REACHED_EXACT
                    completeness = AnalysisCompleteness.COMPLETE
                    truncated = False
                    effective_end = end
                else:
                    status = LimitStatus.EXCEEDED
                    completeness = AnalysisCompleteness.PARTIAL
                    truncated = True
                    first_excluded = distinct_probe[0]
                    # Para tags digitais, effective_end é o timestamp do primeiro evento excluído
                    effective_end = first_excluded.timestamp
            except Exception as exc:
                logger.warning("Overflow probe failed for %s: %s", tag, exc)
                status = LimitStatus.REACHED_UNCONFIRMED
                completeness = AnalysisCompleteness.COMPLETENESS_UNCONFIRMED
                truncated = None

        meta = AnalysisCompletenessMetadata(
            requested_start_time=start,
            requested_end_time=end,
            effective_start_time=effective_start,
            effective_end_time=effective_end,
            returned_point_count=count,
            configured_point_limit=resolution.configured_limit,
            pi_request_safe_limit=resolution.pi_request_safe_limit,
            artifact_safe_row_limit=resolution.artifact_safe_row_limit,
            effective_point_limit=resolution.effective_limit,
            limit_status=status,
            analysis_completeness=completeness,
            truncated=truncated,
            truncation_direction="FROM_WINDOW_START",
            overflow_check_performed=probe_performed,
            unprocessed_start_time=effective_end if truncated else None,
            unprocessed_end_time=end if truncated else None,
        )

        return points, meta, first_excluded

    async def _fetch_interpolated(
        self, tag: str, start: str, end: str
    ) -> list[AnalysisPoint]:
        try:
            raw = await get_interpolated_values_by_tag(tag, start, end, "5m")
            return self._parse_points(raw)
        except Exception as exc:
            logger.warning("Interpolated fetch failed for %s: %s", tag, exc)
            return []

    async def _resolve_digital_set_legacy(
        self, tag: str, item: dict[str, Any]
    ) -> str | None:
        """Adapter legado: consulta atributo ``digitalset`` quando point não tem Set.

        Usado apenas quando o resolver v2 NÃO está ativo (caminho sem ``resolver``).
        """
        from domain.pims.clients.pi_web_api_client import get_point_attributes

        point_type = str(item.get("PointType", "")).lower()
        if point_type != "digital":
            return None

        resolution = resolve_digital_set_name(
            point_data=item,
            digitalset_attribute=None,
        )

        if resolution.source != DigitalSetSource.MISSING:
            return resolution.name

        try:
            attr_raw = await get_point_attributes(tag)
            resolution = resolve_digital_set_name(
                point_data=item,
                digitalset_attribute=attr_raw,
            )
        except Exception as exc:
            msg = str(exc)[:200].lower()
            if "401" in msg or "auth" in msg:
                logger.warning(
                    "digital_set_legacy auth_error tag=%s", tag
                )
            elif "timeout" in msg or "connect" in msg:
                logger.warning(
                    "digital_set_legacy timeout tag=%s", tag
                )
            else:
                logger.warning(
                    "digital_set_legacy error tag=%s error=%s",
                    tag,
                    str(exc)[:200],
                )
            return None

        return resolution.name

    async def _fetch_digital(
        self, tag: str, start: str, end: str, metadata: TagMetadata, item: dict[str, Any]
    ) -> CollectedData | AnalysisError:
        ds = metadata.digital_set

        if not ds:
            ds = await self._resolve_digital_set_legacy(tag, item)

        if not ds:
            return AnalysisError(
                tag=tag,
                code="INVALID_DIGITAL_SET",
                message=(
                    "[INVALID_DIGITAL_SET] O Digital Set não pôde ser resolvido "
                    f"para tag digital '{tag}': campos do PI Point (DigitalSet, "
                    "DigitalSetName) e atributo digitalset ambos ausentes ou inválidos."
                ),
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

        web_id = item.get("WebId", "")

        seed_raw, (recorded, completeness, first_excluded) = await asyncio.gather(
            self._fetch_atorbefore(tag, web_id, start),
            self._fetch_recorded_with_probe(tag, start, end),
        )

        digital_seed = self._parse_single_point(seed_raw)

        initial_state: str | None = None
        first_point = digital_seed if digital_seed is not None else (recorded[0] if recorded else None)
        if first_point is not None:
            first_val = first_point.value
            if first_val is not None:
                idx = int(first_val)
                for s in digital_states:
                    if s.get("indice") == idx:
                        initial_state = s.get("nome")
                        break

        return CollectedData(
            metadata=TagMetadata(
                tag=metadata.tag,
                point_type=metadata.point_type,
                descriptor=metadata.descriptor,
                engineering_units=metadata.engineering_units,
                digital_set=ds,
            ),
            recorded=recorded,
            digital_initial=initial_state,
            digital_states=digital_states,
            digital_seed=digital_seed,
            completeness=completeness,
            first_excluded_point=first_excluded,
        )

    async def _fetch_atorbefore(
        self, tag: str, web_id: str, start: str
    ) -> dict[str, Any]:
        """Obtém o último valor em ou antes de `start` via WebId reutilizado."""
        try:
            return await get_value_at_or_before_by_web_id(web_id, start)
        except Exception as exc:
            logger.warning("AtOrBefore fetch failed for %s: %s", tag, exc)
            return {}

    def _parse_single_point(self, raw: dict[str, Any]) -> AnalysisPoint | None:
        """Extrai um único AnalysisPoint da resposta AtOrBefore (maxCount=1)."""
        items = raw.get("Items") or raw.get("items") or []
        if not isinstance(items, list) or not items:
            return None

        item = items[0]
        ts = item.get("Timestamp")
        val = item.get("Value")
        if ts is None:
            return None

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

        return AnalysisPoint(
            timestamp=str(ts),
            value=value,
            good=bool(good) if good is not None else True,
            questionable=bool(questionable) if questionable is not None else False,
            substituted=bool(substituted) if substituted is not None else False,
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

        dsn = item.get("DigitalSetName")
        if dsn and str(dsn).strip().lower() in INVALID_DIGITAL_SETS:
            dsn = None

        if not digital_set and dsn:
            digital_set = dsn

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

    async def collect_summaries(
        self,
        web_id_to_tag: dict[str, str],
        start_time: str,
        end_time: str,
        summary_types: list[str],
        interval: str | None = None,
        calculation_basis: str = "TimeWeighted",
    ) -> list[BucketSummaryResult]:
        """Coleta estatísticas nativas em lote via GET /streamsets/summary."""
        if not web_id_to_tag or not summary_types:
            return []

        web_ids = list(web_id_to_tag.keys())
        mapper = PiSummaryResponseMapper()
        all_results: list[BucketSummaryResult] = []

        # Dividir em lotes de SUMMARY_BATCH_SIZE
        for i in range(0, len(web_ids), SUMMARY_BATCH_SIZE):
            batch_web_ids = web_ids[i : i + SUMMARY_BATCH_SIZE]
            try:
                payload = await get_streamsets_summary(
                    web_ids=batch_web_ids,
                    summary_types=summary_types,
                    start_time=start_time,
                    end_time=end_time,
                    summary_duration=interval,
                    calculation_basis=calculation_basis,
                )
                mapped = mapper.map_streamsets_summary(
                    payload=payload,
                    web_id_to_tag=web_id_to_tag,
                    calculation_basis=calculation_basis,
                    interval=interval,
                )
                all_results.extend(mapped)
            except Exception as exc:
                logger.error(f"Erro na coleta de summary para o lote {batch_web_ids}: {exc}")

        return all_results

