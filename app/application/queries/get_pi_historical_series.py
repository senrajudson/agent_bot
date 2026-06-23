"""Query: Get historical time series for a PI tag."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.queries.base import Query
from app.domain.enums import TemporalDataMethod
from app.domain.protocols import PIPointRepository, TagSeriesLike
from app.domain.value_objects import (
    CalculationBasis,
    PiWebId,
    SummaryType,
    TimeWindow,
)


@dataclass(frozen=True)
class GetPiHistoricalSeries(Query):
    """Request historical time series data for a PI tag."""

    web_id: PiWebId
    window: TimeWindow
    method: TemporalDataMethod
    interval: str | None = None
    max_count: int | None = None
    summary_type: SummaryType | None = None
    summary_duration: str | None = None
    calculation_basis: CalculationBasis | None = None


@dataclass(frozen=True)
class GetPiHistoricalSeriesResult:
    """Result of historical series query."""

    series: TagSeriesLike


class GetPiHistoricalSeriesHandler:
    """Retrieves historical time series data from PI Web API.

    Delegates to a PIPointRepository (injected via constructor).
    No direct dependency on httpx or PI Web API.
    """

    def __init__(self, repo: PIPointRepository) -> None:
        self._repo = repo

    async def handle(
        self, query: GetPiHistoricalSeries
    ) -> GetPiHistoricalSeriesResult:
        if query.method == TemporalDataMethod.RECORDED:
            series = await self._repo.get_recorded_series(
                query.web_id, query.window, query.max_count or 200000
            )
        elif query.method == TemporalDataMethod.INTERPOLATED:
            series = await self._repo.get_interpolated_series(
                query.web_id, query.window, query.interval or "1m"
            )
        elif query.method == TemporalDataMethod.SUMMARY:
            series = await self._repo.get_summary_series(
                query.web_id,
                query.window,
                query.summary_type or SummaryType.from_string(None),
                query.summary_duration or "1h",
                query.calculation_basis or CalculationBasis.from_string(None),
            )
        else:
            raise ValueError(f"Unknown method: {query.method}")

        return GetPiHistoricalSeriesResult(series=series)
