"""Outbox Dispatcher — consume eventos da outbox com SKIP LOCKED, retry e DLQ.

Este módulo implementa o dispatcher isolado de outbox do bloco EDD.
Ele consome eventos da tabela ``outbox_events``, aplica lock concorrente
via Postgres (``SELECT ... FOR UPDATE SKIP LOCKED``), executa um consumer,
e registra sucesso em ``processed_events`` ou aplica retry/DLQ em falhas.

**Escopo deste Prompt 5**:
- ``OutboxEvent``, ``OutboxDispatchResult``, ``OutboxConsumer``, ``OutboxStore``,
  ``OutboxDispatcher`` e ``PostgresOutboxStore``.
- Testes unitários com fakes (``tests/unit/test_outbox_dispatcher.py``).

**O que NÃO é criado neste módulo**:
- CLI, worker, loop contínuo, scheduler.
- Conexão com ``/chat`` ou ``process_message``.
- Feature flag, env vars reais.
- Conexão com Postgres real (apenas SQL conceitual via fakes nos testes).
"""
from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from app.infrastructure.outbox._error_redaction import sanitize_exception

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutboxEvent:
    """Record interno de item da outbox."""

    outbox_id: int
    event_id: str
    stream_id: str
    stream_version: int
    aggregate_id: str | None
    event_type: str
    event_payload: dict  # já deserializado de JSONB
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    locked_by: str | None
    locked_until: datetime | None
    created_at: datetime
    updated_at: datetime
    correlation_id: str | None
    causation_id: str | None
    metadata: dict | None


@dataclass(frozen=True)
class OutboxDispatchResult:
    """Resumo em memória de uma rodada de dispatch."""

    claimed_count: int
    processed_count: int
    already_processed_count: int
    dispatched_count: int
    retry_count: int
    dlq_count: int


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class OutboxConsumer(Protocol):
    """Contrato do consumidor de eventos."""

    async def handle(self, event: OutboxEvent) -> None: ...


class OutboxStore(Protocol):
    """Contrato de persistência da outbox."""

    async def claim_batch(
        self,
        *,
        worker_id: str,
        batch_size: int,
        lock_ttl_seconds: int,
    ) -> list[OutboxEvent]: ...

    async def is_processed(
        self,
        *,
        consumer_name: str,
        event_id: str,
    ) -> bool: ...

    async def mark_dispatched(
        self,
        *,
        event: OutboxEvent,
        consumer_name: str,
    ) -> None: ...

    async def mark_retry(
        self,
        *,
        event: OutboxEvent,
        error: BaseException,
        delay_seconds: float,
    ) -> None: ...

    async def move_to_dlq(
        self,
        *,
        event: OutboxEvent,
        error: BaseException,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Outbox Dispatcher
# ---------------------------------------------------------------------------


class OutboxDispatcher:
    """Dispatcher isolado de outbox com SKIP LOCKED, retry e DLQ."""

    def __init__(
        self,
        *,
        store: OutboxStore,
        consumer: OutboxConsumer,
        consumer_name: str = "outbox-dispatcher-default",
        worker_id: str | None = None,
        batch_size: int = 50,
        lock_ttl_seconds: int = 30,
        backoff_base_seconds: float = 0.5,
        backoff_factor: float = 2.0,
        backoff_cap_seconds: float = 300.0,
        error_max_length: int = 4096,
    ) -> None:
        if store is None:
            raise ValueError("store is required")
        if consumer is None:
            raise ValueError("consumer is required")
        if not consumer_name or not consumer_name.strip():
            raise ValueError("consumer_name must not be empty")
        if worker_id is not None and (not worker_id or not worker_id.strip()):
            raise ValueError("worker_id must not be empty when provided")
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if lock_ttl_seconds <= 0:
            raise ValueError("lock_ttl_seconds must be > 0")
        if backoff_base_seconds <= 0:
            raise ValueError("backoff_base_seconds must be > 0")
        if backoff_factor < 1.0:
            raise ValueError("backoff_factor must be >= 1.0")
        if backoff_cap_seconds <= 0:
            raise ValueError("backoff_cap_seconds must be > 0")
        if error_max_length <= 0:
            raise ValueError("error_max_length must be > 0")

        self._store = store
        self._consumer = consumer
        self._consumer_name = consumer_name
        self._batch_size = batch_size
        self._lock_ttl_seconds = lock_ttl_seconds
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_factor = backoff_factor
        self._backoff_cap_seconds = backoff_cap_seconds
        self._error_max_length = error_max_length

        if worker_id is not None:
            self._worker_id = worker_id
        else:
            try:
                host = socket.gethostname()
            except Exception:
                host = "unknown"
            self._worker_id = f"{host}-{uuid4().hex[:8]}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _calculate_delay(self, attempts_after_increment: int) -> float:
        raw = self._backoff_base_seconds * (
            self._backoff_factor ** attempts_after_increment
        )
        return min(raw, self._backoff_cap_seconds)

    def _error_class(self, error: BaseException) -> str:
        return error.__class__.__name__

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    async def dispatch_once(self) -> OutboxDispatchResult:
        """Executa uma única rodada de dispatch.

        Política de erro (D23–D30):
        - Erros de ``store.*`` propagam e abortam ``dispatch_once``.
        - Apenas erro de ``consumer.handle`` é capturado e vira retry/DLQ.
        """
        events = await self._store.claim_batch(
            worker_id=self._worker_id,
            batch_size=self._batch_size,
            lock_ttl_seconds=self._lock_ttl_seconds,
        )
        claimed = len(events)
        processed = 0
        already_processed = 0
        dispatched = 0
        retried = 0
        dlq = 0

        for event in events:
            if await self._store.is_processed(
                consumer_name=self._consumer_name,
                event_id=event.event_id,
            ):
                await self._store.mark_dispatched(
                    event=event,
                    consumer_name=self._consumer_name,
                )
                already_processed += 1
                dispatched += 1
                continue

            try:
                await self._consumer.handle(event)
            except Exception as exc:
                attempts_after = event.attempts + 1
                if attempts_after < event.max_attempts:
                    delay = self._calculate_delay(attempts_after)
                    await self._store.mark_retry(
                        event=event,
                        error=exc,
                        delay_seconds=delay,
                    )
                    logger.warning(
                        "outbox_event_retry_scheduled",
                        extra={
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "consumer_name": self._consumer_name,
                            "attempts": attempts_after,
                            "max_attempts": event.max_attempts,
                            "next_attempt_at_seconds": delay,
                            "action": "retry_scheduled",
                            "error_class": exc.__class__.__name__,
                            "sanitized_error": sanitize_exception(exc, max_length=512),
                        },
                    )
                    retried += 1
                else:
                    await self._store.move_to_dlq(
                        event=event,
                        error=exc,
                    )
                    logger.error(
                        "outbox_event_dead_lettered",
                        extra={
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "consumer_name": self._consumer_name,
                            "attempts": attempts_after,
                            "max_attempts": event.max_attempts,
                            "action": "dead_lettered",
                            "error_class": exc.__class__.__name__,
                            "sanitized_error": sanitize_exception(exc, max_length=512),
                        },
                    )
                    dlq += 1
                continue

            await self._store.mark_dispatched(
                event=event,
                consumer_name=self._consumer_name,
            )
            processed += 1
            dispatched += 1

        return OutboxDispatchResult(
            claimed_count=claimed,
            processed_count=processed,
            already_processed_count=already_processed,
            dispatched_count=dispatched,
            retry_count=retried,
            dlq_count=dlq,
        )


# ---------------------------------------------------------------------------
# Postgres Outbox Store
# ---------------------------------------------------------------------------


class PostgresOutboxStore:
    """Implementação concreta do ``OutboxStore`` com asyncpg.

    Recebe ``pool`` por construtor. Não cria pool. Não lê env vars.
    Não conecta no construtor.
    """

    def __init__(self, pool: Any, *, handler_name: str = "outbox-dispatcher-default-handler") -> None:
        self._pool = pool
        self._handler_name = handler_name

    async def claim_batch(
        self,
        *,
        worker_id: str,
        batch_size: int,
        lock_ttl_seconds: int,
    ) -> list[OutboxEvent]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT * FROM outbox_events
                    WHERE (status = 'pending' AND available_at <= NOW())
                       OR (status = 'locked' AND locked_until < NOW())
                    ORDER BY available_at ASC, outbox_id ASC
                    LIMIT $1
                    FOR UPDATE SKIP LOCKED
                    """,
                    batch_size,
                )
                if not rows:
                    return []
                ids = [r["outbox_id"] for r in rows]
                await conn.execute(
                    """
                    UPDATE outbox_events
                    SET status = 'locked',
                        locked_by = $2,
                        locked_until = NOW() + make_interval(secs => $3),
                        updated_at = NOW()
                    WHERE outbox_id = ANY($1::bigint[])
                    """,
                    ids,
                    worker_id,
                    float(lock_ttl_seconds),
                )
                # Re-fetch after UPDATE to return rows with populated
                # status='locked', locked_by, locked_until, updated_at.
                updated_rows = await conn.fetch(
                    """
                    SELECT * FROM outbox_events
                    WHERE outbox_id = ANY($1::bigint[])
                    ORDER BY available_at ASC, outbox_id ASC
                    """,
                    ids,
                )
                return [_row_to_event(r) for r in updated_rows]

    async def is_processed(
        self,
        *,
        consumer_name: str,
        event_id: str,
    ) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM processed_events
                WHERE consumer_name = $1 AND event_id = $2
                LIMIT 1
                """,
                consumer_name,
                event_id,
            )
            return row is not None

    async def mark_dispatched(
        self,
        *,
        event: OutboxEvent,
        consumer_name: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO processed_events
                        (consumer_name, event_id, processed_at, event_type,
                         stream_id, stream_version, outbox_id, handler_name, metadata)
                    VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (consumer_name, event_id) DO NOTHING
                    """,
                    consumer_name,
                    event.event_id,
                    event.event_type,
                    event.stream_id,
                    event.stream_version,
                    event.outbox_id,
                    self._handler_name,
                    json.dumps(event.metadata or {}),
                )
                await conn.execute(
                    """
                    UPDATE outbox_events
                    SET status = 'dispatched',
                        dispatched_at = NOW(),
                        locked_by = NULL,
                        locked_until = NULL,
                        updated_at = NOW()
                    WHERE outbox_id = $1
                    """,
                    event.outbox_id,
                )

    async def mark_retry(
        self,
        *,
        event: OutboxEvent,
        error: BaseException,
        delay_seconds: float,
    ) -> None:
        error_msg = sanitize_exception(error) or error.__class__.__name__
        error_cls = error.__class__.__name__
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE outbox_events
                    SET attempts = $2,
                        status = 'pending',
                        available_at = NOW() + make_interval(secs => $3),
                        locked_by = NULL,
                        locked_until = NULL,
                        last_error = $4,
                        last_error_class = $5,
                        updated_at = NOW()
                    WHERE outbox_id = $1
                    """,
                    event.outbox_id,
                    event.attempts + 1,
                    float(delay_seconds),
                    error_msg,
                    error_cls,
                )

    async def move_to_dlq(
        self,
        *,
        event: OutboxEvent,
        error: BaseException,
    ) -> None:
        error_msg = sanitize_exception(error) or error.__class__.__name__
        error_cls = error.__class__.__name__
        new_attempts = event.attempts + 1
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO outbox_dlq
                        (outbox_id, event_id, stream_id, stream_version, aggregate_id,
                         event_type, event_payload, final_error, final_error_class,
                         attempts, max_attempts, moved_to_dlq_at, original_created_at,
                         correlation_id, causation_id, metadata)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW(),$12,$13,$14,$15)
                    """,
                    event.outbox_id,
                    event.event_id,
                    event.stream_id,
                    event.stream_version,
                    event.aggregate_id,
                    event.event_type,
                    json.dumps(event.event_payload),
                    error_msg,
                    error_cls,
                    new_attempts,
                    event.max_attempts,
                    event.created_at,
                    event.correlation_id,
                    event.causation_id,
                    json.dumps(event.metadata or {}),
                )
                await conn.execute(
                    """
                    UPDATE outbox_events
                    SET status = 'dead_letter',
                        dead_lettered_at = NOW(),
                        attempts = $2,
                        locked_by = NULL,
                        locked_until = NULL,
                        last_error = $3,
                        last_error_class = $4,
                        updated_at = NOW()
                    WHERE outbox_id = $1
                    """,
                    event.outbox_id,
                    new_attempts,
                    error_msg,
                    error_cls,
                )


# ---------------------------------------------------------------------------
# Row → OutboxEvent helper
# ---------------------------------------------------------------------------


def _row_to_event(row: Any) -> OutboxEvent:
    """Converte um registro asyncpg (ou dict fake) em ``OutboxEvent``."""
    payload = row.get("event_payload", {})
    if isinstance(payload, str):
        payload = json.loads(payload)
    metadata = row.get("metadata")
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return OutboxEvent(
        outbox_id=row["outbox_id"],
        event_id=row["event_id"],
        stream_id=row["stream_id"],
        stream_version=row["stream_version"],
        aggregate_id=row.get("aggregate_id"),
        event_type=row["event_type"],
        event_payload=payload,
        status=row["status"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        available_at=row["available_at"],
        locked_by=row.get("locked_by"),
        locked_until=row.get("locked_until"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        correlation_id=row.get("correlation_id"),
        causation_id=row.get("causation_id"),
        metadata=metadata,
    )
