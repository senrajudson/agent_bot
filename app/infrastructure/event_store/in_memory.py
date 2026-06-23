"""In-memory EventStore for tests."""
from __future__ import annotations

from app.domain.events import DomainEvent


class InMemoryEventStore:
    """In-memory append-only event store.

    Events are stored in dict[stream, list[DomainEvent]].
    """

    def __init__(self) -> None:
        self._streams: dict[str, list[DomainEvent]] = {}

    async def append(self, stream: str, event: DomainEvent) -> str:
        self._streams.setdefault(stream, []).append(event)
        return event.event_id

    async def read(self, stream: str, from_id: str = "0") -> list[DomainEvent]:
        return list(self._streams.get(stream, []))

    async def append_batch(self, stream: str, events: list[DomainEvent]) -> list[str]:
        return [await self.append(stream, e) for e in events]
