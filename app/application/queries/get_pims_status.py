"""Query: Get PIMS operational status."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.queries.base import Query
from app.domain.protocols import PimsOpsRepository


@dataclass(frozen=True)
class GetPimsStatus(Query):
    """Request PIMS operational status via Grafana/Loki."""

    lookback_minutes: int | None = None


@dataclass(frozen=True)
class GetPimsStatusResult:
    """Result of PIMS status check."""

    report: dict


class GetPimsStatusHandler:
    """Retrieves PIMS operational status from Grafana/Loki logs.

    Delegates to a PimsOpsRepository (injected via constructor).
    No direct dependency on httpx, Grafana, or Loki.
    """

    def __init__(self, repo: PimsOpsRepository) -> None:
        self._repo = repo

    async def handle(self, query: GetPimsStatus) -> GetPimsStatusResult:
        report = await self._repo.get_status_report(query.lookback_minutes)
        return GetPimsStatusResult(report=report)
