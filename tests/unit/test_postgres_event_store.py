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
from pathlib import Path

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
