"""Tests for OutboxDispatcher — 100% unit tests with fakes."""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxConsumer,
    OutboxDispatchResult,
    OutboxEvent,
    OutboxStore,
    OutboxDispatcher,
    PostgresOutboxStore,
    _truncate,
    _row_to_event,
)


# =========================================================================
# Helpers
# =========================================================================

NOW = datetime.now(timezone.utc)


def _make_event(
    *,
    outbox_id: int = 1,
    event_id: str | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
    status: str = "locked",
    locked_by: str = "worker-1",
) -> OutboxEvent:
    return OutboxEvent(
        outbox_id=outbox_id,
        event_id=event_id or str(uuid4()),
        stream_id="conversation:conv-1",
        stream_version=1,
        aggregate_id=None,
        event_type="InboundMessageReceived",
        event_payload={"message_id": "m1"},
        status=status,
        attempts=attempts,
        max_attempts=max_attempts,
        available_at=NOW,
        locked_by=locked_by,
        locked_until=NOW + timedelta(seconds=30),
        created_at=NOW,
        updated_at=NOW,
        correlation_id=None,
        causation_id=None,
        metadata=None,
    )


# =========================================================================
# Fakes for Dispatcher tests
# =========================================================================


class _FakeConsumer:
    def __init__(self) -> None:
        self.handled: list[OutboxEvent] = []
        self._raise_on: dict[str, Exception] = {}

    def set_raise(self, event_id: str, exc: Exception) -> None:
        self._raise_on[event_id] = exc

    async def handle(self, event: OutboxEvent) -> None:
        self.handled.append(event)
        if event.event_id in self._raise_on:
            raise self._raise_on[event.event_id]


class _FakeStore:
    def __init__(self) -> None:
        self.claimed_events: list[OutboxEvent] = []
        self.processed_checks: list[tuple[str, str]] = []
        self.dispatched_calls: list[tuple[OutboxEvent, str]] = []
        self.retry_calls: list[tuple[OutboxEvent, BaseException, float]] = []
        self.dlq_calls: list[tuple[OutboxEvent, BaseException]] = []
        self._raise_on: dict[str, Exception] = {}

    def set_claim_return(self, events: list[OutboxEvent]) -> None:
        self.claimed_events = events

    def set_raise(self, method: str, exc: Exception) -> None:
        self._raise_on[method] = exc

    async def claim_batch(
        self, *, worker_id: str, batch_size: int, lock_ttl_seconds: int
    ) -> list[OutboxEvent]:
        if "claim_batch" in self._raise_on:
            raise self._raise_on["claim_batch"]
        return self.claimed_events

    async def is_processed(
        self, *, consumer_name: str, event_id: str
    ) -> bool:
        if "is_processed" in self._raise_on:
            raise self._raise_on["is_processed"]
        self.processed_checks.append((consumer_name, event_id))
        return False

    async def mark_dispatched(
        self, *, event: OutboxEvent, consumer_name: str
    ) -> None:
        if "mark_dispatched" in self._raise_on:
            raise self._raise_on["mark_dispatched"]
        self.dispatched_calls.append((event, consumer_name))

    async def mark_retry(
        self, *, event: OutboxEvent, error: BaseException, delay_seconds: float
    ) -> None:
        if "mark_retry" in self._raise_on:
            raise self._raise_on["mark_retry"]
        self.retry_calls.append((event, error, delay_seconds))

    async def move_to_dlq(
        self, *, event: OutboxEvent, error: BaseException
    ) -> None:
        if "move_to_dlq" in self._raise_on:
            raise self._raise_on["move_to_dlq"]
        self.dlq_calls.append((event, error))


# =========================================================================
# Fakes for PostgresOutboxStore tests
# =========================================================================


class _FakeTransaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rolled_back = True
        else:
            self.committed = True
        return False


class _FakeConnection:
    def __init__(
        self,
        *,
        fetch_rows: list[dict] | None = None,
        fetchval_return: Any = None,
        execute_side_effects: list[Exception | None] | None = None,
    ) -> None:
        self.queries: list[tuple[str, tuple]] = []
        self._fetch_rows = fetch_rows or []
        self._fetchval_return = fetchval_return
        self._execute_idx = 0
        self._execute_effects = execute_side_effects or []
        self._transaction = _FakeTransaction()

    def transaction(self) -> _FakeTransaction:
        self._transaction = _FakeTransaction()
        return self._transaction

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        self.queries.append((query, args))
        return self._fetch_rows

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        self.queries.append((query, args))
        if self._fetchval_return is not None:
            return {"?column?": 1} if self._fetchval_return else None
        return None

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.queries.append((query, args))
        return self._fetchval_return

    async def execute(self, query: str, *args: Any) -> str:
        self.queries.append((query, args))
        if self._execute_idx < len(self._execute_effects):
            effect = self._execute_effects[self._execute_idx]
            self._execute_idx += 1
            if isinstance(effect, BaseException):
                raise effect
        return "UPDATE 1"


class _FakeAcquireContext:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakePool:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def acquire(self) -> _FakeAcquireContext:
        return _FakeAcquireContext(self._conn)


# =========================================================================
# Grupo 1 — Contrato e construtor
# =========================================================================


class TestOutboxDispatcherConstructor:
    def test_creates_with_defaults(self) -> None:
        store = _FakeStore()
        consumer = _FakeConsumer()
        d = OutboxDispatcher(store=store, consumer=consumer)
        assert d._consumer_name == "outbox-dispatcher-default"
        assert d._batch_size == 50
        assert d._lock_ttl_seconds == 30
        assert d._backoff_base_seconds == 0.5
        assert d._backoff_factor == 2.0
        assert d._backoff_cap_seconds == 300.0
        assert d._error_max_length == 4096

    def test_worker_id_autogenerated(self) -> None:
        d = OutboxDispatcher(store=_FakeStore(), consumer=_FakeConsumer())
        assert "-" in d._worker_id
        assert len(d._worker_id) > 8

    def test_worker_id_custom(self) -> None:
        d = OutboxDispatcher(
            store=_FakeStore(), consumer=_FakeConsumer(), worker_id="my-worker"
        )
        assert d._worker_id == "my-worker"

    def test_consumer_name_default(self) -> None:
        d = OutboxDispatcher(store=_FakeStore(), consumer=_FakeConsumer())
        assert d._consumer_name == "outbox-dispatcher-default"

    def test_rejects_empty_consumer_name(self) -> None:
        with pytest.raises(ValueError, match="consumer_name"):
            OutboxDispatcher(
                store=_FakeStore(), consumer=_FakeConsumer(), consumer_name=""
            )

    def test_rejects_whitespace_consumer_name(self) -> None:
        with pytest.raises(ValueError, match="consumer_name"):
            OutboxDispatcher(
                store=_FakeStore(), consumer=_FakeConsumer(), consumer_name="  "
            )

    def test_rejects_empty_worker_id(self) -> None:
        with pytest.raises(ValueError, match="worker_id"):
            OutboxDispatcher(
                store=_FakeStore(), consumer=_FakeConsumer(), worker_id=""
            )

    def test_rejects_batch_size_zero(self) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            OutboxDispatcher(
                store=_FakeStore(), consumer=_FakeConsumer(), batch_size=0
            )

    def test_rejects_batch_size_negative(self) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            OutboxDispatcher(
                store=_FakeStore(), consumer=_FakeConsumer(), batch_size=-1
            )

    def test_rejects_lock_ttl_zero(self) -> None:
        with pytest.raises(ValueError, match="lock_ttl_seconds"):
            OutboxDispatcher(
                store=_FakeStore(), consumer=_FakeConsumer(), lock_ttl_seconds=0
            )

    def test_rejects_backoff_base_zero(self) -> None:
        with pytest.raises(ValueError, match="backoff_base_seconds"):
            OutboxDispatcher(
                store=_FakeStore(),
                consumer=_FakeConsumer(),
                backoff_base_seconds=0,
            )

    def test_rejects_backoff_factor_below_one(self) -> None:
        with pytest.raises(ValueError, match="backoff_factor"):
            OutboxDispatcher(
                store=_FakeStore(),
                consumer=_FakeConsumer(),
                backoff_factor=0.5,
            )

    def test_rejects_backoff_cap_zero(self) -> None:
        with pytest.raises(ValueError, match="backoff_cap_seconds"):
            OutboxDispatcher(
                store=_FakeStore(),
                consumer=_FakeConsumer(),
                backoff_cap_seconds=0,
            )

    def test_rejects_error_max_length_zero(self) -> None:
        with pytest.raises(ValueError, match="error_max_length"):
            OutboxDispatcher(
                store=_FakeStore(),
                consumer=_FakeConsumer(),
                error_max_length=0,
            )

    def test_result_has_no_failed_count(self) -> None:
        import dataclasses

        fields = {f.name for f in dataclasses.fields(OutboxDispatchResult)}
        assert "failed_count" not in fields
        assert fields == {
            "claimed_count",
            "processed_count",
            "already_processed_count",
            "dispatched_count",
            "retry_count",
            "dlq_count",
        }


# =========================================================================
# Grupo 2 — dispatch_once
# =========================================================================


class TestDispatchOnce:
    @pytest.mark.asyncio
    async def test_empty_batch_returns_zeros(self) -> None:
        store = _FakeStore()
        store.set_claim_return([])
        d = OutboxDispatcher(store=store, consumer=_FakeConsumer())
        result = await d.dispatch_once()
        assert result.claimed_count == 0
        assert result.processed_count == 0
        assert result.already_processed_count == 0
        assert result.dispatched_count == 0
        assert result.retry_count == 0
        assert result.dlq_count == 0

    @pytest.mark.asyncio
    async def test_already_processed_does_not_call_consumer(self) -> None:
        store = _FakeStore()
        consumer = _FakeConsumer()
        event = _make_event()
        store.set_claim_return([event])

        class _ProcessedStore(_FakeStore):
            async def is_processed(self, **kwargs) -> bool:  # type: ignore
                return True

        store = _ProcessedStore()
        store.set_claim_return([event])
        d = OutboxDispatcher(store=store, consumer=consumer)
        result = await d.dispatch_once()
        assert len(consumer.handled) == 0
        assert result.already_processed_count == 1
        assert result.dispatched_count == 1

    @pytest.mark.asyncio
    async def test_success_calls_consumer_and_dispatches(self) -> None:
        store = _FakeStore()
        consumer = _FakeConsumer()
        event = _make_event()
        store.set_claim_return([event])
        d = OutboxDispatcher(store=store, consumer=consumer)
        result = await d.dispatch_once()
        assert len(consumer.handled) == 1
        assert result.processed_count == 1
        assert result.dispatched_count == 1
        assert len(store.dispatched_calls) == 1

    @pytest.mark.asyncio
    async def test_retryable_error_calls_mark_retry(self) -> None:
        store = _FakeStore()
        consumer = _FakeConsumer()
        event = _make_event(attempts=0, max_attempts=3)
        consumer.set_raise(event.event_id, ValueError("boom"))
        store.set_claim_return([event])
        d = OutboxDispatcher(store=store, consumer=consumer)
        result = await d.dispatch_once()
        assert result.retry_count == 1
        assert result.dlq_count == 0
        assert len(store.retry_calls) == 1

    @pytest.mark.asyncio
    async def test_terminal_error_calls_move_to_dlq(self) -> None:
        store = _FakeStore()
        consumer = _FakeConsumer()
        event = _make_event(attempts=2, max_attempts=3)
        consumer.set_raise(event.event_id, ValueError("terminal"))
        store.set_claim_return([event])
        d = OutboxDispatcher(store=store, consumer=consumer)
        result = await d.dispatch_once()
        assert result.dlq_count == 1
        assert result.retry_count == 0
        assert len(store.dlq_calls) == 1

    @pytest.mark.asyncio
    async def test_mixed_batch_counters(self) -> None:
        consumer = _FakeConsumer()

        e1 = _make_event(outbox_id=1)  # success
        e2 = _make_event(outbox_id=2)  # already processed
        e3 = _make_event(outbox_id=3, attempts=0)  # retry
        e4 = _make_event(outbox_id=4, attempts=2, max_attempts=3)  # dlq

        consumer.set_raise(e3.event_id, ValueError("retry"))
        consumer.set_raise(e4.event_id, ValueError("dlq"))

        already_ids = {e2.event_id}

        class _MixedStore(_FakeStore):
            async def is_processed(self, **kwargs) -> bool:  # type: ignore
                return kwargs.get("event_id") in already_ids

        store = _MixedStore()
        store.set_claim_return([e1, e2, e3, e4])
        d = OutboxDispatcher(store=store, consumer=consumer)
        result = await d.dispatch_once()
        assert result.claimed_count == 4
        assert result.processed_count == 1
        assert result.already_processed_count == 1
        assert result.dispatched_count == 2
        assert result.retry_count == 1
        assert result.dlq_count == 1


# =========================================================================
# Grupo 3 — Política de erro D23-D30
# =========================================================================


class TestErrorPolicy:
    @pytest.mark.asyncio
    async def test_claim_batch_error_propagates(self) -> None:
        store = _FakeStore()
        store.set_raise("claim_batch", RuntimeError("db down"))
        d = OutboxDispatcher(store=store, consumer=_FakeConsumer())
        with pytest.raises(RuntimeError, match="db down"):
            await d.dispatch_once()

    @pytest.mark.asyncio
    async def test_is_processed_error_propagates(self) -> None:
        store = _FakeStore()
        store.set_claim_return([_make_event()])
        store.set_raise("is_processed", RuntimeError("db down"))
        d = OutboxDispatcher(store=store, consumer=_FakeConsumer())
        with pytest.raises(RuntimeError, match="db down"):
            await d.dispatch_once()

    @pytest.mark.asyncio
    async def test_mark_dispatched_error_propagates(self) -> None:
        store = _FakeStore()
        store.set_claim_return([_make_event()])
        store.set_raise("mark_dispatched", RuntimeError("db down"))
        d = OutboxDispatcher(store=store, consumer=_FakeConsumer())
        with pytest.raises(RuntimeError, match="db down"):
            await d.dispatch_once()

    @pytest.mark.asyncio
    async def test_mark_retry_error_propagates(self) -> None:
        store = _FakeStore()
        event = _make_event(attempts=0, max_attempts=3)
        consumer = _FakeConsumer()
        consumer.set_raise(event.event_id, ValueError("err"))
        store.set_claim_return([event])
        store.set_raise("mark_retry", RuntimeError("db down"))
        d = OutboxDispatcher(store=store, consumer=consumer)
        with pytest.raises(RuntimeError, match="db down"):
            await d.dispatch_once()

    @pytest.mark.asyncio
    async def test_move_to_dlq_error_propagates(self) -> None:
        store = _FakeStore()
        event = _make_event(attempts=2, max_attempts=3)
        consumer = _FakeConsumer()
        consumer.set_raise(event.event_id, ValueError("err"))
        store.set_claim_return([event])
        store.set_raise("move_to_dlq", RuntimeError("db down"))
        d = OutboxDispatcher(store=store, consumer=consumer)
        with pytest.raises(RuntimeError, match="db down"):
            await d.dispatch_once()

    @pytest.mark.asyncio
    async def test_consumer_error_does_not_abort_batch(self) -> None:
        store = _FakeStore()
        consumer = _FakeConsumer()

        e1 = _make_event(outbox_id=1, attempts=0, max_attempts=3)
        e2 = _make_event(outbox_id=2)

        consumer.set_raise(e1.event_id, ValueError("err"))
        store.set_claim_return([e1, e2])
        d = OutboxDispatcher(store=store, consumer=consumer)
        result = await d.dispatch_once()
        assert result.retry_count == 1
        assert result.processed_count == 1


# =========================================================================
# Grupo 4 — Backoff/erro
# =========================================================================


class TestHelpers:
    def test_calculate_delay_uses_attempts_after_increment(self) -> None:
        d = OutboxDispatcher(store=_FakeStore(), consumer=_FakeConsumer())
        # delay = 0.5 * (2.0 ** 2) = 2.0
        assert d._calculate_delay(2) == 2.0

    def test_calculate_delay_respects_cap(self) -> None:
        d = OutboxDispatcher(
            store=_FakeStore(),
            consumer=_FakeConsumer(),
            backoff_cap_seconds=5.0,
        )
        # delay = 0.5 * (2.0 ** 10) = 512.0 -> capped to 5.0
        assert d._calculate_delay(10) == 5.0

    def test_calculate_delay_factor_one_is_constant(self) -> None:
        d = OutboxDispatcher(
            store=_FakeStore(),
            consumer=_FakeConsumer(),
            backoff_factor=1.0,
        )
        assert d._calculate_delay(1) == 0.5
        assert d._calculate_delay(5) == 0.5

    def test_truncate_short_message(self) -> None:
        d = OutboxDispatcher(store=_FakeStore(), consumer=_FakeConsumer())
        assert d._truncate_error(ValueError("hi")) == "hi"

    def test_truncate_long_message(self) -> None:
        d = OutboxDispatcher(
            store=_FakeStore(),
            consumer=_FakeConsumer(),
            error_max_length=10,
        )
        assert d._truncate_error(ValueError("a" * 20)) == "a" * 10

    def test_truncate_empty_uses_class(self) -> None:
        d = OutboxDispatcher(store=_FakeStore(), consumer=_FakeConsumer())
        assert d._truncate_error(ValueError("")) == "ValueError"

    def test_error_class(self) -> None:
        d = OutboxDispatcher(store=_FakeStore(), consumer=_FakeConsumer())
        assert d._error_class(ValueError("x")) == "ValueError"

    def test_module_truncate_function(self) -> None:
        assert _truncate("hello", 10) == "hello"
        assert _truncate("hello world long", 5) == "hello"
        assert _truncate("", 10) == "unknown error"


# =========================================================================
# Grupo 5 — PostgresOutboxStore SQL
# =========================================================================


class TestPostgresOutboxStore:
    @pytest.mark.asyncio
    async def test_claim_batch_contains_skip_locked(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        await store.claim_batch(
            worker_id="w1", batch_size=10, lock_ttl_seconds=30
        )
        assert any("FOR UPDATE SKIP LOCKED" in q for q, _ in conn.queries)

    @pytest.mark.asyncio
    async def test_claim_batch_filters_pending_and_locked_expired(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        await store.claim_batch(
            worker_id="w1", batch_size=10, lock_ttl_seconds=30
        )
        claim_query = conn.queries[0][0]
        assert "status = 'pending'" in claim_query
        assert "status = 'locked'" in claim_query
        assert "locked_until < NOW()" in claim_query

    @pytest.mark.asyncio
    async def test_claim_batch_orders_by_available_at(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        await store.claim_batch(
            worker_id="w1", batch_size=10, lock_ttl_seconds=30
        )
        claim_query = conn.queries[0][0]
        assert "ORDER BY available_at ASC, outbox_id ASC" in claim_query

    @pytest.mark.asyncio
    async def test_claim_batch_returns_empty_on_no_rows(self) -> None:
        conn = _FakeConnection(fetch_rows=[])
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        result = await store.claim_batch(
            worker_id="w1", batch_size=10, lock_ttl_seconds=30
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_is_processed_query(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        await store.is_processed(consumer_name="c1", event_id="e1")
        assert any("processed_events" in q for q, _ in conn.queries)

    @pytest.mark.asyncio
    async def test_mark_dispatched_uses_on_conflict(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        event = _make_event()
        await store.mark_dispatched(event=event, consumer_name="c1")
        queries = [q for q, _ in conn.queries]
        assert any("ON CONFLICT" in q for q in queries)
        assert any("dispatched" in q for q in queries)

    @pytest.mark.asyncio
    async def test_mark_retry_uses_pending(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        event = _make_event()
        await store.mark_retry(
            event=event, error=ValueError("err"), delay_seconds=1.0
        )
        queries = [q for q, _ in conn.queries]
        assert any("status = 'pending'" in q for q in queries)
        assert not any("failed" in q for q in queries)

    @pytest.mark.asyncio
    async def test_move_to_dlq_uses_dead_letter(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = PostgresOutboxStore(pool)
        event = _make_event()
        await store.move_to_dlq(event=event, error=ValueError("err"))
        queries = [q for q, _ in conn.queries]
        assert any("dead_letter" in q for q in queries)
        assert any("outbox_dlq" in q for q in queries)
        # "dead_lettered_at" coluna é permitida; verificar ausência do status "failed"
        assert not any("'failed'" in q for q in queries)

    @pytest.mark.asyncio
    async def test_row_to_event(self) -> None:
        row = {
            "outbox_id": 1,
            "event_id": "e1",
            "stream_id": "s1",
            "stream_version": 1,
            "aggregate_id": None,
            "event_type": "TestEvent",
            "event_payload": '{"key": "val"}',
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "available_at": NOW,
            "locked_by": None,
            "locked_until": None,
            "created_at": NOW,
            "updated_at": NOW,
            "correlation_id": None,
            "causation_id": None,
            "metadata": '{"m": 1}',
        }
        event = _row_to_event(row)
        assert event.outbox_id == 1
        assert event.event_payload == {"key": "val"}
        assert event.metadata == {"m": 1}


# =========================================================================
# Grupo 6 — Não-ativação
# =========================================================================


class TestNonActivation:
    def test_no_cli_in_outbox_module(self) -> None:
        import app.infrastructure.outbox.outbox_dispatcher as mod

        source = open(mod.__file__).read()
        assert 'if __name__ == "__main__"' not in source
        assert "asyncio.run" not in source
        assert "while True" not in source

    def test_outbox_dir_has_no_init(self) -> None:
        import os

        outbox_dir = os.path.dirname(
            __import__("app.infrastructure.outbox.outbox_dispatcher", fromlist=[""]).__file__
        )
        assert not os.path.exists(os.path.join(outbox_dir, "__init__.py"))

    def test_orchestrator_uses_null_publisher_default(self) -> None:
        source = open("app/agent/orchestrator.py").read()
        assert "NullEventPublisher()" in source
        assert "InMemoryEventStore(" not in source
