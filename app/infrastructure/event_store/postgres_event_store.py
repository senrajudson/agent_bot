"""PostgreSQL Event Store — append-only, optimistic concurrency per stream.

Requires asyncpg. Only instantiated when EVENT_STORE_BACKEND=postgres.

Note: PostgreSQL Event Store is an OPTIONAL backend in this phase.
The default backend is "memory" (InMemoryEventStore). The /chat endpoint
does not consume this store directly — it instantiates InMemoryEventStore
inline. Connection/pool creation is lazy: the asyncpg pool is created
only on the first real operation (append/read/load_stream).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

try:
    import asyncpg  # type: ignore
except ImportError:
    asyncpg = None  # Lazy import — only needed when backend=postgres

from app.domain.events import DomainEvent, DOMAIN_EVENTS_REGISTRY
from app.infrastructure.event_store.errors import ConcurrencyConflictError

logger = logging.getLogger(__name__)


class PostgresEventStore:
    """PostgreSQL-backed Event Store with optimistic concurrency.

    Uses a single append-only table ``event_store_events`` with a
    UNIQUE(stream_id, stream_version) constraint for concurrency control.
    """

    def __init__(self, dsn: str) -> None:
        if asyncpg is None:
            raise ImportError(
                "asyncpg is required for PostgresEventStore. "
                "Install it with: pip install asyncpg"
            )
        self._dsn = dsn
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        return self._pool

    async def append(
        self,
        stream: str,
        event: DomainEvent,
        expected_version: int | None = None,
    ) -> str:
        """Append a single event to a stream.

        Args:
            stream: Stream identifier (e.g. "conversation:conv-1").
            event: DomainEvent to persist.
            expected_version: If provided, the write succeeds only if the
                current stream version matches. Raises ConcurrencyConflictError otherwise.

        Returns:
            The event_id of the appended event.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Get current max version
                row = await conn.fetchrow(
                    "SELECT COALESCE(MAX(stream_version), 0) AS v "
                    "FROM event_store_events WHERE stream_id = $1",
                    stream,
                )
                current_version = row["v"]

                if expected_version is not None and current_version != expected_version:
                    raise ConcurrencyConflictError(
                        stream_id=stream,
                        expected_version=expected_version,
                        actual_version=current_version,
                    )

                new_version = current_version + 1
                record = self._to_record(event, stream, new_version)

                await conn.execute(
                    """
                    INSERT INTO event_store_events
                        (event_id, stream_id, stream_version, aggregate_id, aggregate_type,
                         event_type, event_version, occurred_at, correlation_id, causation_id,
                         conversation_id, payload, metadata, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
                    """,
                    record["event_id"],
                    record["stream_id"],
                    record["stream_version"],
                    record["aggregate_id"],
                    record["aggregate_type"],
                    record["event_type"],
                    record["event_version"],
                    record["occurred_at"],
                    record["correlation_id"],
                    record["causation_id"],
                    record["conversation_id"],
                    json.dumps(record["payload"]),
                    json.dumps(record["metadata"]),
                )

        return event.event_id

    async def append_batch(
        self,
        stream: str,
        events: list[DomainEvent],
        expected_version: int | None = None,
    ) -> list[str]:
        """Append multiple events atomically."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT COALESCE(MAX(stream_version), 0) AS v "
                    "FROM event_store_events WHERE stream_id = $1",
                    stream,
                )
                current_version = row["v"]

                if expected_version is not None and current_version != expected_version:
                    raise ConcurrencyConflictError(
                        stream_id=stream,
                        expected_version=expected_version,
                        actual_version=current_version,
                    )

                version = current_version
                ids = []
                for event in events:
                    version += 1
                    record = self._to_record(event, stream, version)
                    await conn.execute(
                        """
                        INSERT INTO event_store_events
                            (event_id, stream_id, stream_version, aggregate_id, aggregate_type,
                             event_type, event_version, occurred_at, correlation_id, causation_id,
                             conversation_id, payload, metadata, created_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
                        """,
                        record["event_id"],
                        record["stream_id"],
                        record["stream_version"],
                        record["aggregate_id"],
                        record["aggregate_type"],
                        record["event_type"],
                        record["event_version"],
                        record["occurred_at"],
                        record["correlation_id"],
                        record["causation_id"],
                        record["conversation_id"],
                        json.dumps(record["payload"]),
                        json.dumps(record["metadata"]),
                    )
                    ids.append(event.event_id)

        return ids

    async def read(self, stream: str, from_id: str = "0") -> list[DomainEvent]:
        """Read all events from a stream (legacy interface)."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT * FROM event_store_events WHERE stream_id = $1 ORDER BY stream_version ASC",
            stream,
        )
        return [self._from_record(dict(row)) for row in rows]

    async def load_stream(
        self, stream_id: str, from_version: int | None = None
    ) -> list[DomainEvent]:
        """Load events from a stream, optionally starting from a version."""
        pool = await self._get_pool()
        if from_version is not None:
            rows = await pool.fetch(
                "SELECT * FROM event_store_events "
                "WHERE stream_id = $1 AND stream_version >= $2 "
                "ORDER BY stream_version ASC",
                stream_id, from_version,
            )
        else:
            rows = await pool.fetch(
                "SELECT * FROM event_store_events WHERE stream_id = $1 "
                "ORDER BY stream_version ASC",
                stream_id,
            )
        return [self._from_record(dict(row)) for row in rows]

    async def load_by_correlation_id(
        self, correlation_id: str
    ) -> list[DomainEvent]:
        """Load all events sharing the same correlation_id."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT * FROM event_store_events WHERE correlation_id = $1 "
            "ORDER BY occurred_at ASC",
            correlation_id,
        )
        return [self._from_record(dict(row)) for row in rows]

    async def load_by_event_type(
        self, event_type: str, limit: int = 100
    ) -> list[DomainEvent]:
        """Load events by type (most recent first)."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT * FROM event_store_events WHERE event_type = $1 "
            "ORDER BY occurred_at DESC LIMIT $2",
            event_type, limit,
        )
        return [self._from_record(dict(row)) for row in reversed(rows)]

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_record(
        event: DomainEvent, stream: str, version: int
    ) -> dict[str, Any]:
        """Convert a DomainEvent to a database record dict."""
        payload = event._payload()
        return {
            "event_id": event.event_id,
            "stream_id": stream,
            "stream_version": version,
            "aggregate_id": event.aggregate_id or "",
            "aggregate_type": event.aggregate_type or "",
            "event_type": event.event_type,
            "event_version": event.event_version,
            "occurred_at": event.occurred_at,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "conversation_id": event.conversation_id,
            "payload": payload,
            "metadata": event.metadata,
        }

    @staticmethod
    def _from_record(row: dict) -> DomainEvent:
        """Reconstruct a DomainEvent from a database record."""
        event_type_name = row.get("event_type", "DomainEvent")
        cls = DOMAIN_EVENTS_REGISTRY.get(event_type_name)

        payload = row.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        occurred_at = row.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)
        if occurred_at and occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)

        if cls is not None:
            # Build kwargs from payload (sub-class fields) + envelope
            valid_fields = set(cls.__dataclass_fields__.keys())
            init_kwargs = {}
            for k, v in payload.items():
                if k in valid_fields:
                    init_kwargs[k] = v
            # Set envelope fields
            for env_field in (
                "event_id", "event_type", "event_version", "occurred_at",
                "aggregate_id", "aggregate_type", "correlation_id",
                "causation_id", "conversation_id",
            ):
                val = row.get(env_field)
                if env_field == "occurred_at":
                    val = occurred_at
                if val is not None and env_field in valid_fields:
                    init_kwargs[env_field] = val
            if "metadata" in valid_fields:
                init_kwargs["metadata"] = metadata
            try:
                return cls(**init_kwargs)
            except TypeError:
                pass

        # Fallback: return base DomainEvent
        return DomainEvent(
            event_id=row.get("event_id", ""),
            occurred_at=occurred_at or datetime.now(timezone.utc),
            conversation_id=row.get("conversation_id"),
            correlation_id=row.get("correlation_id"),
        )
