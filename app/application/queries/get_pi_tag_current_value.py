"""Query: Get current value of a PI tag."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.application.queries.base import Query
from app.domain.errors import TagNotFoundError
from app.domain.protocols import PIPointRepository, PiPointLike, PiTagValueLike


@dataclass(frozen=True)
class GetPiTagCurrentValue(Query):
    """Request the current value of a PI tag."""

    tag: str


@dataclass(frozen=True)
class DigitalStateLike:
    """Minimal digital state representation."""

    index: int
    name: str
    description: str


@dataclass(frozen=True)
class GetPiTagCurrentValueResult:
    """Result of PI tag current value query."""

    point: PiPointLike
    value: PiTagValueLike | None
    digital_states: list[DigitalStateLike] = field(default_factory=list)


class GetPiTagCurrentValueHandler:
    """Retrieves the current value and metadata of a PI tag.

    Delegates to a PIPointRepository (injected via constructor).
    No direct dependency on httpx or PI Web API.
    """

    def __init__(self, repo: PIPointRepository) -> None:
        self._repo = repo

    async def handle(
        self, query: GetPiTagCurrentValue
    ) -> GetPiTagCurrentValueResult:
        try:
            point = await self._repo.get_point_by_tag(query.tag)
        except Exception as exc:
            raise TagNotFoundError(query.tag) from exc

        from app.domain.value_objects import PiWebId

        value = await self._repo.get_current_value(PiWebId(point.web_id))
        return GetPiTagCurrentValueResult(
            point=point, value=value, digital_states=[]
        )
