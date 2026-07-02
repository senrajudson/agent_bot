"""Integration tests for TransactionalPostgresEventStore against real Postgres.

Covers D17 scenarios from the Prompt 6 specification.

These tests do NOT touch /chat, the orchestrator, the Saga, the EventPublisher,
or the factory. They only validate the isolated store against the real schema.
"""
from __future__ import annotations

import json

import asyncpg
import pytest

from app.domain.events import AgentRouteSelected
from app.domain.projections import (
    AssistantMessageRecorded,
    UserMessageRecorded,
)
from app.infrastructure.event_store.transactional_postgres_event_store import (
    TransactionalPostgresEventStore,
)
from tests.integration.edd.conftest import (
    fetch_all,
    fetch_one,
    make_agent_event,
    make_test_event,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# D17 — append creates rows in both tables
# ---------------------------------------------------------------------------


async def test_append_creates_event_store_row(pg_pool: asyncpg.Pool) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()
    await store.append("test-stream", event)

    row = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    assert row is not None
    assert row["stream_id"] == "test-stream"
    assert row["stream_version"] == 1
    assert row["event_type"] == "DomainEvent"


async def test_append_creates_outbox_row(pg_pool: asyncpg.Pool) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()
    await store.append("test-stream", event)

    row = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert row is not None
    assert row["stream_id"] == "test-stream"
    assert row["stream_version"] == 1
    assert row["event_type"] == "DomainEvent"


async def test_append_uses_same_event_id_in_both_tables(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()
    await store.append("test-stream", event)

    es = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert es is not None and ob is not None
    assert es["event_id"] == ob["event_id"]


async def test_append_uses_same_stream_version_in_both_tables(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()
    await store.append("test-stream", event)

    es = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert es is not None and ob is not None
    assert es["stream_version"] == ob["stream_version"]


async def test_append_outbox_status_is_pending(pg_pool: asyncpg.Pool) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()
    await store.append("test-stream", event)

    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert ob is not None
    assert ob["status"] == "pending"


async def test_append_outbox_attempts_is_zero(pg_pool: asyncpg.Pool) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()
    await store.append("test-stream", event)

    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert ob is not None
    assert ob["attempts"] == 0


async def test_append_outbox_max_attempts_default_is_three(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()
    await store.append("test-stream", event)

    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert ob is not None
    assert ob["max_attempts"] == 3


async def test_append_aggregate_id_none_is_empty_string_in_event_store(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()  # aggregate_id=None default
    await store.append("test-stream", event)

    es = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    assert es is not None
    assert es["aggregate_id"] == ""


async def test_append_aggregate_id_none_is_null_in_outbox(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event()  # aggregate_id=None default
    await store.append("test-stream", event)

    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert ob is not None
    assert ob["aggregate_id"] is None


async def test_append_payload_is_preserved_as_json(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_agent_event(route="pims", message_id="m-99", latency_ms=42)
    await store.append("test-stream", event)

    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert ob is not None
    payload_raw = ob["event_payload"]
    payload = (
        json.loads(payload_raw)
        if isinstance(payload_raw, str)
        else payload_raw
    )
    assert payload["route"] == "pims"
    assert payload["message_id"] == "m-99"
    assert payload["latency_ms"] == 42
    assert "event_id" not in payload
    assert "event_type" not in payload
    assert "occurred_at" not in payload


async def test_append_metadata_is_preserved_as_json(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event(metadata={"k": "v", "n": 1})
    await store.append("test-stream", event)

    es = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    assert es is not None
    metadata = es["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    assert metadata == {"k": "v", "n": 1}


async def test_append_correlation_id_preserved(pg_pool: asyncpg.Pool) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event(correlation_id="corr-1")
    await store.append("test-stream", event)

    es = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert es is not None and ob is not None
    assert es["correlation_id"] == "corr-1"
    assert ob["correlation_id"] == "corr-1"


async def test_append_causation_id_preserved(pg_pool: asyncpg.Pool) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event(causation_id="cause-1")
    await store.append("test-stream", event)

    es = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    ob = await fetch_one(pg_pool, "outbox_events", event_id=event.event_id)
    assert es is not None and ob is not None
    assert es["causation_id"] == "cause-1"
    assert ob["causation_id"] == "cause-1"


async def test_append_conversation_id_preserved(pg_pool: asyncpg.Pool) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_test_event(conversation_id="conv-7")
    await store.append("test-stream", event)

    es = await fetch_one(pg_pool, "event_store_events", event_id=event.event_id)
    assert es is not None
    assert es["conversation_id"] == "conv-7"
    # outbox_events does not have conversation_id; verify only event_store_events


async def test_append_batch_creates_multiple_pairs(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    events = [make_test_event() for _ in range(3)]
    await store.append_batch("test-stream", events)

    for e in events:
        es = await fetch_one(pg_pool, "event_store_events", event_id=e.event_id)
        ob = await fetch_one(pg_pool, "outbox_events", event_id=e.event_id)
        assert es is not None, f"event_store row missing for {e.event_id}"
        assert ob is not None, f"outbox row missing for {e.event_id}"


async def test_append_batch_returns_event_ids_in_input_order(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    events = [make_test_event() for _ in range(5)]
    result = await store.append_batch("test-stream", events)
    assert result == [e.event_id for e in events]


async def test_read_returns_events_ordered_by_stream_version_asc(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    e1 = make_test_event()
    e2 = make_test_event()
    e3 = make_test_event()
    await store.append("ordered-stream", e1)
    await store.append("ordered-stream", e2)
    await store.append("ordered-stream", e3)

    rows = await fetch_all(pg_pool, "event_store_events", order_by="stream_version")
    # rows can include any other events; filter by stream_id
    stream_rows = [r for r in rows if r["stream_id"] == "ordered-stream"]
    assert len(stream_rows) == 3
    assert [str(r["event_id"]) for r in stream_rows] == [e1.event_id, e2.event_id, e3.event_id]


async def test_read_reconstructs_event_type_from_registry(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = make_agent_event(route="pims", message_id="m-1", latency_ms=10)
    await store.append("reg-stream", event)

    events = await store.read("reg-stream")
    assert len(events) == 1
    assert isinstance(events[0], AgentRouteSelected)
    assert events[0].route == "pims"
    assert events[0].message_id == "m-1"
    assert events[0].latency_ms == 10


# ---------------------------------------------------------------------------
# D17d — Projection events (UserMessageRecorded, AssistantMessageRecorded)
# ---------------------------------------------------------------------------


async def test_append_user_message_recorded_persists_in_event_store(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = UserMessageRecorded(content="hi", created_at="t1")
    event_id = await store.append("edd-proj-stream", event)

    row = await fetch_one(pg_pool, "event_store_events", event_id=event_id)
    assert row is not None
    assert row["aggregate_id"] == ""
    assert row["aggregate_type"] == ""
    assert row["event_type"] == "UserMessageRecorded"
    assert row["event_version"] == 1


async def test_append_user_message_recorded_persists_in_outbox(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = UserMessageRecorded(content="hi", created_at="t1")
    event_id = await store.append("edd-proj-stream", event)

    row = await fetch_one(pg_pool, "outbox_events", event_id=event_id)
    assert row is not None
    assert row["aggregate_id"] is None
    assert row["event_type"] == "UserMessageRecorded"


async def test_append_assistant_message_recorded_persists_in_event_store(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = AssistantMessageRecorded(
        content="resp", created_at="t2", metadata={"tool_name": "x"},
    )
    event_id = await store.append("edd-proj-stream", event)

    row = await fetch_one(pg_pool, "event_store_events", event_id=event_id)
    assert row is not None
    assert row["event_type"] == "AssistantMessageRecorded"
    assert row["aggregate_id"] == ""
    assert row["aggregate_type"] == ""

    # Metadata column must contain the full metadata dict
    meta = row["metadata"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    assert meta == {"tool_name": "x"}

    # Payload column must NOT contain the metadata dict
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload == {"content": "resp", "created_at": "t2"}
    assert "tool_name" not in payload


async def test_append_assistant_message_recorded_persists_in_outbox(
    pg_pool: asyncpg.Pool,
) -> None:
    store = TransactionalPostgresEventStore(pool=pg_pool)
    event = AssistantMessageRecorded(
        content="resp", created_at="t2", metadata={"tool_name": "x"},
    )
    event_id = await store.append("edd-proj-stream", event)

    row = await fetch_one(pg_pool, "outbox_events", event_id=event_id)
    assert row is not None
    assert row["event_type"] == "AssistantMessageRecorded"
    assert row["aggregate_id"] is None

    meta = row["metadata"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    assert meta == {"tool_name": "x"}

    payload = row["event_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload == {"content": "resp", "created_at": "t2"}
    assert "tool_name" not in payload
