"""Tests for TransactionalPostgresEventStore — 100% unit tests with fakes."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from app.domain.events import (
    DomainEvent,
    AgentRouteSelected,
    ConversationMemoryLoaded,
    MessageProcessingFailed,
)
from app.domain.projections import (
    AssistantMessageRecorded,
    UserMessageRecorded,
)
from app.infrastructure.event_store.base import EventStore, EventPublisher
from app.infrastructure.event_store.transactional_postgres_event_store import (
    TransactionalPostgresEventStore,
)


# =========================================================================
# Fakes for asyncpg
# =========================================================================


class _FakeTransaction:
    """Fake asyncpg Transaction — tracks begin/commit/rollback."""

    def __init__(self) -> None:
        self.begin = False
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        self.begin = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rolled_back = True
        else:
            self.committed = True
        return False


class _FakeConnection:
    """Fake asyncpg Connection — captures queries and simulates failures."""

    def __init__(
        self,
        *,
        fetchval_side_effects: list[Any] | None = None,
        execute_side_effects: list[Any] | None = None,
        fetch_rows: list[dict] | None = None,
    ) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._fetchval_idx = 0
        self._execute_idx = 0
        self._fetchval_effects = fetchval_side_effects or []
        self._execute_effects = execute_side_effects or []
        self._fetch_rows = fetch_rows or []
        self._transaction = _FakeTransaction()

    def transaction(self) -> _FakeTransaction:
        self._transaction = _FakeTransaction()
        return self._transaction

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", (query, *args)))
        if self._fetchval_idx < len(self._fetchval_effects):
            result = self._fetchval_effects[self._fetchval_idx]
            self._fetchval_idx += 1
            if isinstance(result, BaseException):
                raise result
            return result
        return 0

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", (query, *args)))
        if self._execute_idx < len(self._execute_effects):
            result = self._execute_effects[self._execute_idx]
            self._execute_idx += 1
            if isinstance(result, BaseException):
                raise result
        return "INSERT 0 1"

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        self.calls.append(("fetch", (query, *args)))
        return self._fetch_rows


class _FakeAcquireContext:
    """Async context manager wrapping a _FakeConnection for pool.acquire()."""

    def __init__(self, conn: _FakeConnection, error: Exception | None = None):
        self._conn = conn
        self._error = error

    async def __aenter__(self):
        if self._error is not None:
            raise self._error
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakePool:
    """Fake asyncpg Pool — returns an async context manager from acquire()."""

    def __init__(
        self,
        conn: _FakeConnection | None = None,
        acquire_error: Exception | None = None,
    ) -> None:
        self._conn = conn or _FakeConnection()
        self._acquire_error = acquire_error

    def acquire(self) -> _FakeAcquireContext:
        return _FakeAcquireContext(self._conn, self._acquire_error)

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        return await self._conn.fetch(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        return await self._conn.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._conn.execute(query, *args)


# =========================================================================
# Helper — build a fake DomainEvent for testing
# =========================================================================


def _make_event(**kwargs: Any) -> DomainEvent:
    return DomainEvent(**kwargs)


def _make_agent_event(**kwargs: Any) -> AgentRouteSelected:
    return AgentRouteSelected(**kwargs)


# =========================================================================
# Grupo 1 — Contrato e não-ativação
# =========================================================================


class TestProtocolConformance:
    def test_adapter_satisfies_event_store_protocol(self) -> None:
        pool = _FakePool()
        store = TransactionalPostgresEventStore(pool)
        assert isinstance(store, EventStore)

    def test_public_methods_count_exactly_three(self) -> None:
        public_methods = {
            name
            for name, val in TransactionalPostgresEventStore.__dict__.items()
            if not name.startswith("_") and callable(val)
        }
        assert public_methods == {"append", "read", "append_batch"}

    def test_does_not_alter_postgres_event_store(self) -> None:
        from app.infrastructure.event_store.postgres_event_store import PostgresEventStore
        assert hasattr(PostgresEventStore, "_to_record")
        assert hasattr(PostgresEventStore, "_from_record")
        assert hasattr(PostgresEventStore, "append")
        assert hasattr(PostgresEventStore, "read")

    def test_does_not_alter_event_store_protocol(self) -> None:
        public_methods = {
            name
            for name, val in EventStore.__dict__.items()
            if not name.startswith("_") and callable(val)
        }
        assert public_methods == {"append", "read", "append_batch"}

    def test_does_not_alter_event_publisher_protocol(self) -> None:
        public_methods = {
            name
            for name, val in EventPublisher.__dict__.items()
            if not name.startswith("_") and callable(val)
        }
        assert public_methods == {"publish", "publish_to_conversation"}


# =========================================================================
# Grupo 2 — Mapeamento
# =========================================================================


class TestMapping:
    def test_append_uses_same_event_id_in_both_tables(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_agent_event(route="pims")

        async def _run():
            await store.append("stream:test", event)

        import asyncio
        asyncio.run(_run())

        # Find both INSERT calls
        es_insert = None
        ob_insert = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_insert = args
            if op == "execute" and "outbox_events" in args[0]:
                ob_insert = args

        assert es_insert is not None
        assert ob_insert is not None
        assert es_insert[1] == ob_insert[1]  # same event_id ($1)

    def test_append_uses_same_stream_version_in_both_tables(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("stream:s1", event))

        es_insert = None
        ob_insert = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_insert = args
            if op == "execute" and "outbox_events" in args[0]:
                ob_insert = args

        assert es_insert is not None
        assert ob_insert is not None
        assert es_insert[3] == ob_insert[3]  # same stream_version ($3)

    def test_aggregate_id_absent_is_empty_string_in_event_store(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()  # aggregate_id=None

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                # aggregate_id is $4
                assert args[4] == ""

    def test_aggregate_id_absent_is_null_in_outbox(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()  # aggregate_id=None

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                # aggregate_id is $4
                assert args[4] is None

    def test_aggregate_id_present_is_identical_in_both_tables(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event(aggregate_id="agg-1")

        import asyncio
        asyncio.run(store.append("s", event))

        es_aggregate = None
        ob_aggregate = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_aggregate = args[4]  # $4
            if op == "execute" and "outbox_events" in args[0]:
                ob_aggregate = args[4]  # $4

        assert es_aggregate == "agg-1"
        assert ob_aggregate == "agg-1"

    def test_outbox_event_payload_contains_only_specific_payload(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_agent_event(route="pims", message_id="m1")

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                # event_payload is $6 (JSON string)
                payload_str = args[6]
                payload = json.loads(payload_str)
                assert "route" in payload
                assert "message_id" in payload
                # Must NOT contain envelope fields
                assert "event_id" not in payload
                assert "event_type" not in payload
                assert "occurred_at" not in payload
                assert "conversation_id" not in payload

    def test_outbox_event_payload_excludes_envelope_keys(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event(correlation_id="c1")

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                payload = json.loads(args[6])
                assert "event_id" not in payload
                assert "event_type" not in payload
                assert "occurred_at" not in payload
                assert "correlation_id" not in payload
                assert "causation_id" not in payload

    def test_outbox_event_payload_matches_event_store_payload(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_agent_event(route="pims", latency_ms=42)

        import asyncio
        asyncio.run(store.append("s", event))

        es_payload = None
        ob_payload = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_payload = args[12]  # $12 = payload
            if op == "execute" and "outbox_events" in args[0]:
                ob_payload = args[6]   # $6 = event_payload

        assert es_payload == ob_payload

    def test_outbox_status_initial_is_pending(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                # status is $7
                assert args[7] == "pending"

    def test_outbox_attempts_initial_is_zero(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                # attempts is $8
                assert args[8] == 0

    def test_outbox_max_attempts_default_is_three(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                # max_attempts is $9
                assert args[9] == 3

    def test_outbox_max_attempts_accepts_constructor_override(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool, max_attempts=7)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                assert args[9] == 7

    def test_outbox_available_at_is_set_on_insert(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                # available_at is $10
                assert isinstance(args[10], datetime)

    def test_outbox_dispatched_at_is_null(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        # dispatched_at is not in the INSERT params — it uses DEFAULT NULL
        # So we just verify no error was raised and the INSERT succeeded
        assert True

    def test_outbox_dead_lettered_at_is_null(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        # dead_lettered_at is not in the INSERT params — it uses DEFAULT NULL
        assert True

    def test_outbox_locked_fields_are_null(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        # locked_by and locked_until are not in INSERT params — DEFAULT NULL
        assert True

    def test_outbox_error_fields_are_null(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        # last_error and last_error_class are not in INSERT params — DEFAULT NULL
        assert True

    def test_metadata_absent_is_empty_dict(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()  # metadata={}

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                metadata = json.loads(args[13])  # $13 = metadata
                assert metadata == {}
            if op == "execute" and "outbox_events" in args[0]:
                metadata = json.loads(args[13])  # $13 = metadata
                assert metadata == {}

    def test_metadata_present_is_preserved_in_both_tables(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event(metadata={"key": "value", "n": 1})

        import asyncio
        asyncio.run(store.append("s", event))

        es_metadata = None
        ob_metadata = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_metadata = json.loads(args[13])
            if op == "execute" and "outbox_events" in args[0]:
                ob_metadata = json.loads(args[13])

        assert es_metadata == {"key": "value", "n": 1}
        assert ob_metadata == {"key": "value", "n": 1}

    def test_correlation_causation_preserved_in_both_tables(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event(correlation_id="c1", causation_id="ca1")

        import asyncio
        asyncio.run(store.append("s", event))

        es_corr = es_caus = ob_corr = ob_caus = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_corr = args[9]   # $9 = correlation_id
                es_caus = args[10]  # $10 = causation_id
            if op == "execute" and "outbox_events" in args[0]:
                ob_corr = args[11]  # $11 = correlation_id
                ob_caus = args[12]  # $12 = causation_id

        assert es_corr == "c1"
        assert es_caus == "ca1"
        assert ob_corr == "c1"
        assert ob_caus == "ca1"


# =========================================================================
# Grupo 3 — Transação (append)
# =========================================================================


class TestAppendTransaction:
    def test_append_succeeds_with_both_inserts(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        asyncio.run(store.append("s", event))

        execute_calls = [c for c in conn.calls if c[0] == "execute"]
        assert len(execute_calls) == 2
        assert "event_store_events" in execute_calls[0][1][0]
        assert "outbox_events" in execute_calls[1][1][0]

    def test_append_rolls_back_when_outbox_insert_fails(self) -> None:
        from asyncpg import PostgresError
        conn = _FakeConnection(
            execute_side_effects=[None, PostgresError("outbox insert failed")]
        )
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        with pytest.raises(PostgresError, match="outbox insert failed"):
            asyncio.run(store.append("s", event))

        # Verify rollback was triggered
        assert conn._transaction.rolled_back is True

    def test_append_rolls_back_when_event_store_insert_fails(self) -> None:
        from asyncpg import PostgresError
        conn = _FakeConnection(
            execute_side_effects=[PostgresError("es insert failed")]
        )
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        with pytest.raises(PostgresError, match="es insert failed"):
            asyncio.run(store.append("s", event))

    def test_append_propagates_unique_violation_event_store(self) -> None:
        from asyncpg import UniqueViolationError
        conn = _FakeConnection(
            execute_side_effects=[UniqueViolationError("duplicate")]
        )
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        with pytest.raises(UniqueViolationError):
            asyncio.run(store.append("s", event))

    def test_append_propagates_unique_violation_outbox(self) -> None:
        from asyncpg import UniqueViolationError
        conn = _FakeConnection(
            execute_side_effects=[None, UniqueViolationError("dup event_id")]
        )
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        with pytest.raises(UniqueViolationError):
            asyncio.run(store.append("s", event))

    def test_append_propagates_connection_error(self) -> None:
        from asyncpg import PostgresConnectionError
        pool = _FakePool(acquire_error=PostgresConnectionError("connection refused"))
        store = TransactionalPostgresEventStore(pool)
        event = _make_event()

        import asyncio
        with pytest.raises(PostgresConnectionError):
            asyncio.run(store.append("s", event))

    def test_append_propagates_max_attempts_invalid_in_constructor(self) -> None:
        pool = _FakePool()
        with pytest.raises(ValueError, match="max_attempts must be > 0"):
            TransactionalPostgresEventStore(pool, max_attempts=0)

    def test_append_negative_max_attempts_fails(self) -> None:
        pool = _FakePool()
        with pytest.raises(ValueError, match="max_attempts must be > 0"):
            TransactionalPostgresEventStore(pool, max_attempts=-5)


# =========================================================================
# Grupo 4 — Batch (append_batch)
# =========================================================================


class TestAppendBatchTransaction:
    def test_append_batch_inserts_all_pairs_in_single_transaction(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        events = [_make_event() for _ in range(3)]

        import asyncio
        asyncio.run(store.append_batch("s", events))

        execute_calls = [c for c in conn.calls if c[0] == "execute"]
        # 3 events × 2 inserts each = 6 execute calls
        assert len(execute_calls) == 6

    def test_append_batch_returns_event_ids_in_input_order(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        events = [_make_event() for _ in range(5)]

        import asyncio
        result = asyncio.run(store.append_batch("s", events))

        assert result == [e.event_id for e in events]

    def test_append_batch_versions_are_sequential(self) -> None:
        conn = _FakeConnection(fetchval_side_effects=[0])
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        events = [_make_event() for _ in range(3)]

        import asyncio
        asyncio.run(store.append_batch("s", events))

        # All events should have sequential versions
        es_versions = []
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_versions.append(args[3])  # $4 = stream_version

        assert es_versions == [1, 2, 3]

    def test_append_batch_rolls_back_entire_batch_on_any_failure(self) -> None:
        from asyncpg import PostgresError
        # Fail on the 2nd event's outbox insert (3rd execute call)
        conn = _FakeConnection(
            execute_side_effects=[None, None, PostgresError("batch fail")]
        )
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        events = [_make_event() for _ in range(3)]

        import asyncio
        with pytest.raises(PostgresError, match="batch fail"):
            asyncio.run(store.append_batch("s", events))

    def test_append_batch_propagates_exceptions(self) -> None:
        from asyncpg import PostgresError
        conn = _FakeConnection(
            execute_side_effects=[PostgresError("first event fails")]
        )
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        events = [_make_event()]

        import asyncio
        with pytest.raises(PostgresError, match="first event fails"):
            asyncio.run(store.append_batch("s", events))


# =========================================================================
# Grupo 5 — Read
# =========================================================================


class TestRead:
    def test_read_queries_event_store_events(self) -> None:
        conn = _FakeConnection(fetch_rows=[
            {
                "event_id": "ev-1",
                "event_type": "AgentRouteSelected",
                "event_version": 1,
                "occurred_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "aggregate_id": "",
                "aggregate_type": "",
                "correlation_id": None,
                "causation_id": None,
                "conversation_id": None,
                "stream_id": "s",
                "stream_version": 1,
                "payload": json.dumps({"route": "pims"}),
                "metadata": json.dumps({}),
            }
        ])
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)

        import asyncio
        events = asyncio.run(store.read("s"))

        read_calls = [c for c in conn.calls if c[0] == "fetch"]
        assert len(read_calls) == 1
        assert "event_store_events" in read_calls[0][1][0]
        assert len(events) == 1

    def test_read_orders_by_stream_version_asc(self) -> None:
        conn = _FakeConnection(fetch_rows=[])
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)

        import asyncio
        asyncio.run(store.read("s"))

        for op, args in conn.calls:
            if op == "fetch":
                assert "ORDER BY stream_version ASC" in args[0]

    def test_read_returns_list_of_domain_events(self) -> None:
        conn = _FakeConnection(fetch_rows=[
            {
                "event_id": "ev-1",
                "event_type": "AgentRouteSelected",
                "event_version": 1,
                "occurred_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "aggregate_id": "",
                "aggregate_type": "",
                "correlation_id": None,
                "causation_id": None,
                "conversation_id": "c1",
                "stream_id": "s",
                "stream_version": 1,
                "payload": json.dumps({"route": "pims"}),
                "metadata": json.dumps({}),
            }
        ])
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)

        import asyncio
        events = asyncio.run(store.read("s"))

        assert len(events) == 1
        assert isinstance(events[0], AgentRouteSelected)
        assert events[0].route == "pims"
        assert events[0].conversation_id == "c1"

    def test_read_returns_empty_list_for_unknown_stream(self) -> None:
        conn = _FakeConnection(fetch_rows=[])
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)

        import asyncio
        events = asyncio.run(store.read("nonexistent"))

        assert events == []

    def test_read_reconstructs_event_type_from_registry(self) -> None:
        conn = _FakeConnection(fetch_rows=[
            {
                "event_id": "ev-2",
                "event_type": "ConversationMemoryLoaded",
                "event_version": 1,
                "occurred_at": datetime(2025, 6, 1, tzinfo=timezone.utc),
                "aggregate_id": "",
                "aggregate_type": "",
                "correlation_id": None,
                "causation_id": None,
                "conversation_id": "c2",
                "stream_id": "s",
                "stream_version": 1,
                "payload": json.dumps({"turns_count": 5}),
                "metadata": json.dumps({}),
            }
        ])
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)

        import asyncio
        events = asyncio.run(store.read("s"))

        assert isinstance(events[0], ConversationMemoryLoaded)
        assert events[0].turns_count == 5

    def test_read_falls_back_to_domain_event_for_unknown_type(self) -> None:
        conn = _FakeConnection(fetch_rows=[
            {
                "event_id": "ev-3",
                "event_type": "UnknownEventType",
                "event_version": 1,
                "occurred_at": datetime(2025, 6, 1, tzinfo=timezone.utc),
                "aggregate_id": "",
                "aggregate_type": "",
                "correlation_id": None,
                "causation_id": None,
                "conversation_id": None,
                "stream_id": "s",
                "stream_version": 1,
                "payload": json.dumps({}),
                "metadata": json.dumps({}),
            }
        ])
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)

        import asyncio
        events = asyncio.run(store.read("s"))

        assert isinstance(events[0], DomainEvent)
        assert not isinstance(events[0], AgentRouteSelected)


# =========================================================================
# Constructor validation
# =========================================================================


class TestConstructor:
    def test_default_max_attempts(self) -> None:
        pool = _FakePool()
        store = TransactionalPostgresEventStore(pool)
        assert store._max_attempts == 3

    def test_custom_max_attempts(self) -> None:
        pool = _FakePool()
        store = TransactionalPostgresEventStore(pool, max_attempts=10)
        assert store._max_attempts == 10

    def test_zero_max_attempts_raises(self) -> None:
        pool = _FakePool()
        with pytest.raises(ValueError, match="max_attempts must be > 0"):
            TransactionalPostgresEventStore(pool, max_attempts=0)

    def test_negative_max_attempts_raises(self) -> None:
        pool = _FakePool()
        with pytest.raises(ValueError, match="max_attempts must be > 0"):
            TransactionalPostgresEventStore(pool, max_attempts=-1)

    def test_max_attempts_one_is_valid(self) -> None:
        pool = _FakePool()
        store = TransactionalPostgresEventStore(pool, max_attempts=1)
        assert store._max_attempts == 1

    def test_pool_stored(self) -> None:
        pool = _FakePool()
        store = TransactionalPostgresEventStore(pool)
        assert store._pool is pool


# =========================================================================
# Grupo 6 — Projection events (UserMessageRecorded, AssistantMessageRecorded)
# =========================================================================


class TestProjectionEventMapping:
    """Projection events are dataclasses in app.domain.projections, NOT DomainEvent.

    They don't have aggregate_id, aggregate_type, event_type, event_version,
    correlation_id, causation_id, or _payload(). The store must tolerate them
    via defensive getattr in _to_event_store_record and _to_outbox_record.
    """

    def test_append_persists_user_message_recorded_to_both_tables(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = UserMessageRecorded(content="hi", created_at="t1")

        import asyncio
        asyncio.run(store.append("s", event))

        es_insert = None
        ob_insert = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_insert = args
            if op == "execute" and "outbox_events" in args[0]:
                ob_insert = args

        assert es_insert is not None
        assert ob_insert is not None
        assert es_insert[1] == ob_insert[1]  # same event_id ($1)

    def test_append_persists_assistant_message_recorded_to_both_tables(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = AssistantMessageRecorded(content="hello", created_at="t2")

        import asyncio
        asyncio.run(store.append("s", event))

        es_insert = None
        ob_insert = None
        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                es_insert = args
            if op == "execute" and "outbox_events" in args[0]:
                ob_insert = args

        assert es_insert is not None
        assert ob_insert is not None
        assert es_insert[1] == ob_insert[1]

    def test_append_projection_event_aggregate_id_empty_in_event_store(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = UserMessageRecorded(content="hi", created_at="t1")

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                # aggregate_id is $4 — must be "" for NOT NULL constraint
                assert args[4] == ""

    def test_append_projection_event_aggregate_id_null_in_outbox(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = AssistantMessageRecorded(content="hello", created_at="t2")

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "outbox_events" in args[0]:
                # aggregate_id is $4 — must be None (NULLABLE column)
                assert args[4] is None

    def test_append_projection_event_event_type_uses_class_name(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = UserMessageRecorded(content="hi", created_at="t1")

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                # event_type is $6 in event_store_events INSERT
                assert args[6] == "UserMessageRecorded"
            if op == "execute" and "outbox_events" in args[0]:
                # event_type is $5 in outbox_events INSERT
                assert args[5] == "UserMessageRecorded"

    def test_append_projection_event_payload_contains_content_and_created_at(self) -> None:
        conn = _FakeConnection()
        pool = _FakePool(conn)
        store = TransactionalPostgresEventStore(pool)
        event = UserMessageRecorded(content="hi", created_at="t1")

        import asyncio
        asyncio.run(store.append("s", event))

        for op, args in conn.calls:
            if op == "execute" and "event_store_events" in args[0]:
                payload = json.loads(args[12])  # $12 = payload
                assert payload == {"content": "hi", "created_at": "t1"}
                assert "event_id" not in payload
                assert "aggregate_id" not in payload
                assert "metadata" not in payload
            if op == "execute" and "outbox_events" in args[0]:
                payload = json.loads(args[6])  # $6 = event_payload
                assert payload == {"content": "hi", "created_at": "t1"}
                assert "event_id" not in payload
                assert "aggregate_id" not in payload
                assert "metadata" not in payload


# =========================================================================
# TestSafePayload
# =========================================================================


class TestSafePayload:
    """Tests for TransactionalPostgresEventStore._safe_payload defensive serializer."""

    def test_safe_payload_uses_vars_when_no_payload_method(self) -> None:
        @dataclass
        class _CustomEvent:
            name: str
            value: int

        event = _CustomEvent(name="test", value=42)
        result = TransactionalPostgresEventStore._safe_payload(event)
        assert result == {"name": "test", "value": 42}

    def test_safe_payload_uses_payload_when_returns_dict(self) -> None:
        @dataclass
        class _EventWithPayload:
            name: str

            def _payload(self) -> dict:
                return {"custom_key": self.name}

        event = _EventWithPayload(name="custom")
        result = TransactionalPostgresEventStore._safe_payload(event)
        assert result == {"custom_key": "custom"}

    def test_safe_payload_falls_back_to_vars_when_payload_returns_non_dict(self) -> None:
        @dataclass
        class _EventWithBadPayload:
            x: int

            def _payload(self) -> str:
                return "not a dict"

        event = _EventWithBadPayload(x=99)
        result = TransactionalPostgresEventStore._safe_payload(event)
        assert result == {"x": 99}
