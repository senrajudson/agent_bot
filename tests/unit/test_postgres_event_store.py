"""Unit tests for the optional PostgreSQL Event Store backend.

These tests verify:
- PostgresEventStore is importable from the canonical package path.
- PostgresEventStore can be instantiated WITHOUT opening an asyncpg pool.
- The factory selects the correct backend based on EVENT_STORE_BACKEND.
- The DDL file contains the expected columns and constraints.
- The DomainEvent envelope (TASK-002) produces the expected 11 keys and
  JSON-serializable payload/metadata.

No real Postgres connection. No Docker. No testcontainers. No network.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest


# ---------------------------------------------------------------------------
# 1. Canonical import path
# ---------------------------------------------------------------------------
class TestPostgresEventStoreImport:
    def test_importable_from_canonical_path(self) -> None:
        from app.infrastructure.event_store import PostgresEventStore
        assert PostgresEventStore is not None
        assert PostgresEventStore.__name__ == "PostgresEventStore"

    def test_module_does_not_open_pool_on_import(self) -> None:
        from app.infrastructure.event_store import PostgresEventStore
        assert isinstance(PostgresEventStore, type)


# ---------------------------------------------------------------------------
# 2. Lazy connection: no pool open on __init__
# ---------------------------------------------------------------------------
class TestPostgresEventStoreInstantiation:
    def test_init_does_not_open_pool(self) -> None:
        from app.infrastructure.event_store import PostgresEventStore
        store = PostgresEventStore(dsn="postgresql://fake:fake@localhost:5432/fake")
        assert store._pool is None  # noqa: SLF001 — explicit internal check

    def test_init_accepts_dsn_only(self) -> None:
        from app.infrastructure.event_store import PostgresEventStore
        store = PostgresEventStore(dsn="postgresql://u:p@h:5432/db")
        assert store._dsn.endswith("db")  # noqa: SLF001


# ---------------------------------------------------------------------------
# 3. Factory: default backend = InMemoryEventStore
# ---------------------------------------------------------------------------
class TestFactoryDefault:
    def setup_method(self) -> None:
        self._old_backend = os.environ.pop("EVENT_STORE_BACKEND", None)
        self._old_dsn = os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)

    def teardown_method(self) -> None:
        for k, v in (
            ("EVENT_STORE_BACKEND", self._old_backend),
            ("EVENT_STORE_POSTGRES_DSN", self._old_dsn),
        ):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_default_returns_in_memory(self) -> None:
        from app.infrastructure.event_store.factory import get_event_store
        from app.infrastructure.event_store.in_memory import InMemoryEventStore
        store = get_event_store()
        assert isinstance(store, InMemoryEventStore)


# ---------------------------------------------------------------------------
# 4. Factory: postgres with DSN
# ---------------------------------------------------------------------------
class TestFactoryPostgresWithDSN:
    def setup_method(self) -> None:
        self._old_backend = os.environ.pop("EVENT_STORE_BACKEND", None)
        self._old_dsn = os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)
        os.environ["EVENT_STORE_BACKEND"] = "postgres"
        os.environ["EVENT_STORE_POSTGRES_DSN"] = "postgresql://u:p@h:5432/db"

    def teardown_method(self) -> None:
        for k in ("EVENT_STORE_BACKEND", "EVENT_STORE_POSTGRES_DSN"):
            os.environ.pop(k, None)
        if self._old_backend is not None:
            os.environ["EVENT_STORE_BACKEND"] = self._old_backend
        if self._old_dsn is not None:
            os.environ["EVENT_STORE_POSTGRES_DSN"] = self._old_dsn

    def test_returns_postgres_event_store(self) -> None:
        from app.infrastructure.event_store import PostgresEventStore
        from app.infrastructure.event_store.factory import get_event_store
        store = get_event_store()
        assert isinstance(store, PostgresEventStore)
        assert store._pool is None  # noqa: SLF001 — no pool opened


# ---------------------------------------------------------------------------
# 5. Factory: postgres without DSN raises ValueError
# ---------------------------------------------------------------------------
class TestFactoryPostgresWithoutDSN:
    def setup_method(self) -> None:
        self._old_backend = os.environ.pop("EVENT_STORE_BACKEND", None)
        self._old_dsn = os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)
        os.environ["EVENT_STORE_BACKEND"] = "postgres"
        os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)

    def teardown_method(self) -> None:
        for k in ("EVENT_STORE_BACKEND", "EVENT_STORE_POSTGRES_DSN"):
            os.environ.pop(k, None)
        if self._old_backend is not None:
            os.environ["EVENT_STORE_BACKEND"] = self._old_backend
        if self._old_dsn is not None:
            os.environ["EVENT_STORE_POSTGRES_DSN"] = self._old_dsn

    def test_raises_value_error(self) -> None:
        from app.infrastructure.event_store.factory import get_event_store
        with pytest.raises(ValueError) as exc_info:
            get_event_store()
        assert "EVENT_STORE_POSTGRES_DSN" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. DDL: column and constraint presence (read as plain text)
# ---------------------------------------------------------------------------
DDL_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "infrastructure"
    / "event_store"
    / "sql"
    / "001_create_event_store_events.sql"
)


class TestDDL:
    @pytest.fixture(scope="class")
    def ddl_text(self) -> str:
        assert DDL_PATH.exists(), f"DDL not found at {DDL_PATH}"
        return DDL_PATH.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "column",
        [
            "event_id",
            "stream_id",
            "stream_version",
            "event_type",
            "event_version",
            "occurred_at",
            "conversation_id",
            "aggregate_id",
            "aggregate_type",
            "correlation_id",
            "causation_id",
            "payload",
            "metadata",
            "created_at",
        ],
    )
    def test_ddl_contains_column(self, ddl_text: str, column: str) -> None:
        assert column in ddl_text, f"DDL is missing column: {column}"

    def test_ddl_has_event_id_primary_key(self, ddl_text: str) -> None:
        assert "event_id" in ddl_text
        assert "PRIMARY KEY" in ddl_text

    def test_ddl_has_unique_stream_version(self, ddl_text: str) -> None:
        assert "UNIQUE" in ddl_text
        assert "stream_id" in ddl_text
        assert "stream_version" in ddl_text

    @pytest.mark.parametrize(
        "index_token",
        [
            "stream_id",
            "stream_version",
            "correlation_id",
            "event_type",
            "occurred_at",
        ],
    )
    def test_ddl_has_index_tokens(self, ddl_text: str, index_token: str) -> None:
        assert index_token in ddl_text


# ---------------------------------------------------------------------------
# 7. DomainEvent envelope (TASK-002): 11 keys + JSON-serializable
# ---------------------------------------------------------------------------
class TestDomainEventEnvelope:
    def test_to_event_record_has_11_keys(self) -> None:
        from app.domain.events import DomainEvent
        record = DomainEvent().to_event_record()
        assert len(record) == 11
        expected = {
            "event_id",
            "event_type",
            "event_version",
            "occurred_at",
            "aggregate_id",
            "aggregate_type",
            "correlation_id",
            "causation_id",
            "conversation_id",
            "payload",
            "metadata",
        }
        assert set(record.keys()) == expected

    def test_payload_and_metadata_are_json_serializable(self) -> None:
        from app.domain.events import DomainEvent
        record = DomainEvent(
            correlation_id="c1",
            aggregate_id="a1",
            aggregate_type="Conversation",
            metadata={"k": "v", "n": 1, "lst": [1, 2]},
        ).to_event_record()
        assert json.dumps(record["payload"]) == "{}"
        assert json.loads(json.dumps(record["metadata"])) == {
            "k": "v",
            "n": 1,
            "lst": [1, 2],
        }

    def test_specific_event_payload_is_json_serializable(self) -> None:
        from app.domain.enums import AggregateType
        from app.domain.events import AgentRunStarted

        e = AgentRunStarted(
            run_id="r1",
            agent_type="pi",
            route="pims",
            correlation_id="c1",
            aggregate_id="a1",
            aggregate_type=AggregateType.AGENT_RUN.value,
        )
        record = e.to_event_record()
        s = json.dumps(record)
        parsed = json.loads(s)
        assert parsed["payload"]["run_id"] == "r1"
        assert parsed["payload"]["agent_type"] == "pi"
        assert parsed["aggregate_type"] == "AgentRun"


# ---------------------------------------------------------------------------
# 8. Factory: unknown backend falls back to InMemory
# ---------------------------------------------------------------------------
class TestFactoryUnknownBackend:
    def test_unknown_backend_returns_in_memory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EVENT_STORE_BACKEND with unknown value falls back to InMemoryEventStore."""
        from app.infrastructure.event_store.factory import get_event_store
        from app.infrastructure.event_store.in_memory import InMemoryEventStore

        monkeypatch.delenv("EVENT_STORE_BACKEND", raising=False)
        monkeypatch.delenv("EVENT_STORE_POSTGRES_DSN", raising=False)
        monkeypatch.setenv("EVENT_STORE_BACKEND", "unknown_xyz")
        store = get_event_store()
        assert isinstance(store, InMemoryEventStore)


# ---------------------------------------------------------------------------
# 9. Factory: redis_streams failure falls back to InMemory
# ---------------------------------------------------------------------------
class TestFactoryRedisStreamsFallback:
    def test_redis_streams_fallback_to_in_memory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """redis_streams backend with connection failure falls back to InMemoryEventStore."""
        from app.infrastructure.event_store.factory import get_event_store
        from app.infrastructure.event_store.in_memory import InMemoryEventStore

        monkeypatch.delenv("EVENT_STORE_BACKEND", raising=False)
        monkeypatch.delenv("EVENT_STORE_POSTGRES_DSN", raising=False)
        monkeypatch.setenv("EVENT_STORE_BACKEND", "redis_streams")
        monkeypatch.setattr(
            "app.clients.redis_client.get_redis_client",
            Mock(side_effect=ConnectionError("Redis down")),
        )
        store = get_event_store()
        assert isinstance(store, InMemoryEventStore)


# ---------------------------------------------------------------------------
# 10. _to_record: 13 keys with correct mapping
# ---------------------------------------------------------------------------
class TestToRecord:
    def test_to_record_produces_13_keys_with_expected_mapping(self) -> None:
        """_to_record maps DomainEvent envelope to a 13-key dict.

        Note: the DDL has 14 columns (including created_at), but created_at
        is set by the database (NOW()), not by _to_record. This is expected.
        """
        from app.domain.events import AgentRouteSelected
        from app.infrastructure.event_store.postgres_event_store import PostgresEventStore

        event = AgentRouteSelected(route="pims", correlation_id="c1")
        record = PostgresEventStore._to_record(event, "stream:s1", 1)

        assert len(record) == 13
        expected_keys = {
            "event_id", "stream_id", "stream_version",
            "aggregate_id", "aggregate_type",
            "event_type", "event_version", "occurred_at",
            "correlation_id", "causation_id", "conversation_id",
            "payload", "metadata",
        }
        assert set(record.keys()) == expected_keys
        assert record["stream_id"] == "stream:s1"
        assert record["stream_version"] == 1
        assert record["event_type"] == "AgentRouteSelected"
        assert record["payload"] == {"message_id": "", "route": "pims", "latency_ms": 0}
        assert record["aggregate_id"] == ""


# ---------------------------------------------------------------------------
# 11. _from_record: known event type
# ---------------------------------------------------------------------------
class TestFromRecord:
    def test_from_record_reconstructs_known_event_type(self) -> None:
        """_from_record reconstructs AgentRouteSelected from a row dict."""
        from app.domain.events import AgentRouteSelected
        from app.infrastructure.event_store.postgres_event_store import PostgresEventStore

        row = {
            "event_id": "test-id-123",
            "event_type": "AgentRouteSelected",
            "event_version": 1,
            "occurred_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "aggregate_id": "a1",
            "aggregate_type": "AgentRun",
            "correlation_id": "c1",
            "causation_id": None,
            "conversation_id": "conv-1",
            "payload": {"route": "pims"},
            "metadata": {},
        }
        result = PostgresEventStore._from_record(row)
        assert isinstance(result, AgentRouteSelected)
        assert result.route == "pims"
        assert result.correlation_id == "c1"
        assert result.event_id == "test-id-123"


# ---------------------------------------------------------------------------
# 12. _from_record: unknown event type falls back to DomainEvent
# ---------------------------------------------------------------------------
class TestFromRecordFallback:
    def test_unknown_event_type_falls_back_to_base_domain_event(self) -> None:
        """_from_record with unknown event_type returns base DomainEvent."""
        from app.domain.events import AgentRouteSelected, DomainEvent
        from app.infrastructure.event_store.postgres_event_store import PostgresEventStore

        row = {
            "event_id": "fallback-id",
            "event_type": "NonExistentEventType",
            "event_version": 1,
            "occurred_at": datetime(2025, 6, 1, tzinfo=timezone.utc),
            "aggregate_id": "",
            "aggregate_type": "",
            "correlation_id": None,
            "causation_id": None,
            "conversation_id": None,
            "payload": {},
            "metadata": {},
        }
        result = PostgresEventStore._from_record(row)
        assert isinstance(result, DomainEvent)
        assert not isinstance(result, AgentRouteSelected)
        assert result.event_id == "fallback-id"


# ---------------------------------------------------------------------------
# 13. asyncpg optional: ImportError when asyncpg is None
# ---------------------------------------------------------------------------
class TestAsyncpgOptional:
    def test_init_raises_import_error_when_asyncpg_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PostgresEventStore raises ImportError when asyncpg is None."""
        from app.infrastructure.event_store.postgres_event_store import PostgresEventStore

        monkeypatch.setattr(
            "app.infrastructure.event_store.postgres_event_store.asyncpg", None
        )
        with pytest.raises(ImportError, match="asyncpg"):
            PostgresEventStore(dsn="postgresql://fake:fake@localhost:5432/fake")


# ---------------------------------------------------------------------------
# 14. ConcurrencyConflictError
# ---------------------------------------------------------------------------
class TestConcurrencyConflictError:
    def test_error_has_expected_fields(self) -> None:
        """ConcurrencyConflictError has stream_id, expected_version, actual_version."""
        from app.infrastructure.event_store.errors import ConcurrencyConflictError

        err = ConcurrencyConflictError(
            stream_id="s1", expected_version=5, actual_version=3
        )
        assert err.stream_id == "s1"
        assert err.expected_version == 5
        assert err.actual_version == 3
        assert isinstance(err, Exception)
        assert "s1" in str(err)
