"""Transactional Postgres Event Store — grava event_store_events + outbox_events em uma única transação.

Implementa o EventStore Protocol atual. Não cria pool. Não acessa env vars.
Não faz fallback. Não engole exceções.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.domain.events import DomainEvent, DOMAIN_EVENTS_REGISTRY


class TransactionalPostgresEventStore:
    """EventStore que persiste em event_store_events + outbox_events.

    Grava os dois registros em uma única transação Postgres.
    Recebe pool via construtor. Não cria pool. Não acessa env vars.
    Não faz fallback. Não engole exceções.
    """

    _SQL_NEXT_VERSION = (
        "SELECT COALESCE(MAX(stream_version), 0) AS v "
        "FROM event_store_events WHERE stream_id = $1"
    )

    _SQL_INSERT_EVENT_STORE = (
        "INSERT INTO event_store_events "
        "(event_id, stream_id, stream_version, aggregate_id, aggregate_type, "
        "event_type, event_version, occurred_at, correlation_id, causation_id, "
        "conversation_id, payload, metadata) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)"
    )

    _SQL_INSERT_OUTBOX = (
        "INSERT INTO outbox_events "
        "(event_id, stream_id, stream_version, aggregate_id, event_type, "
        "event_payload, status, attempts, max_attempts, available_at, "
        "correlation_id, causation_id, metadata) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)"
    )

    _SQL_READ_EVENT_STORE = (
        "SELECT * FROM event_store_events WHERE stream_id = $1 "
        "ORDER BY stream_version ASC"
    )

    def __init__(self, pool: Any, max_attempts: int = 3) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be > 0")
        self._pool = pool
        self._max_attempts = max_attempts

    # ------------------------------------------------------------------
    # Public API (EventStore Protocol — 3 methods)
    # ------------------------------------------------------------------

    async def append(self, stream: str, event: DomainEvent) -> str:
        """Append a single event, writing to event_store_events + outbox_events atomically."""
        pool = self._pool
        resolved_id = getattr(event, "event_id", "") or str(uuid.uuid4())
        async with pool.acquire() as conn:
            async with conn.transaction():
                version = await self._next_stream_version(conn, stream)

                record_es = self._to_event_store_record(event, stream, version, resolved_id)
                await conn.execute(
                    self._SQL_INSERT_EVENT_STORE,
                    record_es["event_id"],
                    record_es["stream_id"],
                    record_es["stream_version"],
                    record_es["aggregate_id"],
                    record_es["aggregate_type"],
                    record_es["event_type"],
                    record_es["event_version"],
                    record_es["occurred_at"],
                    record_es["correlation_id"],
                    record_es["causation_id"],
                    record_es["conversation_id"],
                    record_es["payload"],
                    record_es["metadata"],
                )

                record_ob = self._to_outbox_record(event, stream, version, self._max_attempts, resolved_id)
                await conn.execute(
                    self._SQL_INSERT_OUTBOX,
                    record_ob["event_id"],
                    record_ob["stream_id"],
                    record_ob["stream_version"],
                    record_ob["aggregate_id"],
                    record_ob["event_type"],
                    record_ob["event_payload"],
                    record_ob["status"],
                    record_ob["attempts"],
                    record_ob["max_attempts"],
                    record_ob["available_at"],
                    record_ob["correlation_id"],
                    record_ob["causation_id"],
                    record_ob["metadata"],
                )

        return resolved_id

    async def append_batch(self, stream: str, events: list[DomainEvent]) -> list[str]:
        """Append multiple events atomically, writing to both tables per event."""
        pool = self._pool
        async with pool.acquire() as conn:
            async with conn.transaction():
                version = await self._next_stream_version(conn, stream)

                ids: list[str] = []
                for event in events:
                    resolved_id = getattr(event, "event_id", "") or str(uuid.uuid4())
                    record_es = self._to_event_store_record(event, stream, version, resolved_id)
                    await conn.execute(
                        self._SQL_INSERT_EVENT_STORE,
                        record_es["event_id"],
                        record_es["stream_id"],
                        record_es["stream_version"],
                        record_es["aggregate_id"],
                        record_es["aggregate_type"],
                        record_es["event_type"],
                        record_es["event_version"],
                        record_es["occurred_at"],
                        record_es["correlation_id"],
                        record_es["causation_id"],
                        record_es["conversation_id"],
                        record_es["payload"],
                        record_es["metadata"],
                    )

                    record_ob = self._to_outbox_record(event, stream, version, self._max_attempts, resolved_id)
                    await conn.execute(
                        self._SQL_INSERT_OUTBOX,
                        record_ob["event_id"],
                        record_ob["stream_id"],
                        record_ob["stream_version"],
                        record_ob["aggregate_id"],
                        record_ob["event_type"],
                        record_ob["event_payload"],
                        record_ob["status"],
                        record_ob["attempts"],
                        record_ob["max_attempts"],
                        record_ob["available_at"],
                        record_ob["correlation_id"],
                        record_ob["causation_id"],
                        record_ob["metadata"],
                    )

                    ids.append(resolved_id)
                    version += 1

        return ids

    async def read(self, stream: str, from_id: str = "0") -> list[DomainEvent]:
        """Read events from event_store_events only, ordered by stream_version ASC."""
        pool = self._pool
        rows = await pool.fetch(self._SQL_READ_EVENT_STORE, stream)
        return [self._from_record(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _next_stream_version(conn: Any, stream: str) -> int:
        """Calculate next stream_version via MAX + 1."""
        row = await conn.fetchval(
            "SELECT COALESCE(MAX(stream_version), 0) AS v "
            "FROM event_store_events WHERE stream_id = $1",
            stream,
        )
        return int(row) + 1

    @staticmethod
    def _to_event_store_record(
        event: DomainEvent, stream: str, version: int, event_id: str
    ) -> dict[str, Any]:
        """Map DomainEvent to a record for event_store_events.

        Uses getattr defensively to tolerate events that don't have the
        full DomainEvent envelope (e.g. UserMessageRecorded).
        """
        return {
            "event_id": event_id,
            "stream_id": stream,
            "stream_version": version,
            "aggregate_id": getattr(event, "aggregate_id", "") or "",
            "aggregate_type": getattr(event, "aggregate_type", "") or "",
            "event_type": getattr(event, "event_type", type(event).__name__),
            "event_version": getattr(event, "event_version", 1),
            "occurred_at": getattr(event, "occurred_at"),
            "correlation_id": getattr(event, "correlation_id", None),
            "causation_id": getattr(event, "causation_id", None),
            "conversation_id": getattr(event, "conversation_id", None),
            "payload": json.dumps(TransactionalPostgresEventStore._safe_payload(event)),
            "metadata": json.dumps(getattr(event, "metadata", {}) or {}),
        }

    @staticmethod
    def _to_outbox_record(
        event: DomainEvent, stream: str, version: int, max_attempts: int, event_id: str
    ) -> dict[str, Any]:
        """Map DomainEvent to a record for outbox_events."""
        return {
            "event_id": event_id,
            "stream_id": stream,
            "stream_version": version,
            "aggregate_id": getattr(event, "aggregate_id", None),
            "event_type": getattr(event, "event_type", type(event).__name__),
            "event_payload": json.dumps(TransactionalPostgresEventStore._safe_payload(event)),
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
            "available_at": datetime.now(timezone.utc),
            "correlation_id": getattr(event, "correlation_id", None),
            "causation_id": getattr(event, "causation_id", None),
            "metadata": json.dumps(getattr(event, "metadata", {}) or {}),
        }

    @staticmethod
    def _safe_payload(event: Any) -> dict:
        """Extract JSONB payload for event_store_events.payload and outbox_events.event_payload.

        Strategy:
          1. If event has _payload() method (DomainEvent subclasses), invoke it.
          2. Otherwise, derive from vars(event) filtered by envelope fields.
        """
        if hasattr(event, "_payload") and callable(event._payload):
            result = event._payload()
            if isinstance(result, dict):
                return result
        envelope_fields = {
            "event_id", "event_type", "event_version", "occurred_at",
            "aggregate_id", "aggregate_type", "correlation_id",
            "causation_id", "conversation_id", "metadata",
        }
        return {k: v for k, v in vars(event).items() if k not in envelope_fields}

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
            valid_fields = set(cls.__dataclass_fields__.keys())
            init_kwargs: dict[str, Any] = {}
            for k, v in payload.items():
                if k in valid_fields:
                    init_kwargs[k] = v
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

        return DomainEvent(
            event_id=row.get("event_id", ""),
            occurred_at=occurred_at or datetime.now(timezone.utc),
            conversation_id=row.get("conversation_id"),
            correlation_id=row.get("correlation_id"),
        )
