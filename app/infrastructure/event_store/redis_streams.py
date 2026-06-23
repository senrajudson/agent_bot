"""Redis Streams-backed EventStore."""
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from app.domain.events import DomainEvent, DOMAIN_EVENTS_REGISTRY


class RedisStreamsEventStore:
    """Redis Streams append-only event store.

    Uses XADD/XRANGE. Each stream is a Redis key "events:{stream}".
    """

    def __init__(self, redis: Redis, key_prefix: str = "events") -> None:
        self._redis = redis
        self._prefix = key_prefix

    def _key(self, stream: str) -> str:
        return f"{self._prefix}:{stream}"

    async def append(self, stream: str, event: DomainEvent) -> str:
        key = self._key(stream)
        flat = self._serialize(event)
        await self._redis.xadd(key, flat)
        return event.event_id

    async def read(self, stream: str, from_id: str = "0") -> list[DomainEvent]:
        key = self._key(stream)
        results = await self._redis.xrange(key, min=from_id, max="+")
        return [self._deserialize(msg_id, fields) for msg_id, fields in results]

    async def append_batch(self, stream: str, events: list[DomainEvent]) -> list[str]:
        return [await self.append(stream, e) for e in events]

    @staticmethod
    def _serialize(event: DomainEvent) -> dict[str, str]:
        payload = event.to_dict()
        return {k: json.dumps(v) for k, v in payload.items()}

    @staticmethod
    def _deserialize(msg_id: bytes | str, fields: dict[bytes, bytes]) -> DomainEvent:
        data = {}
        for k, v in fields.items():
            key = k.decode() if isinstance(k, bytes) else k
            try:
                data[key] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                data[key] = v.decode() if isinstance(v, bytes) else v

        event_type_name = data.pop("event_type", "DomainEvent")
        cls = DOMAIN_EVENTS_REGISTRY.get(event_type_name, DomainEvent)

        if cls is DomainEvent:
            return DomainEvent(
                event_id=data.get("event_id", ""),
                conversation_id=data.get("conversation_id"),
                correlation_id=data.get("correlation_id"),
            )

        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)
