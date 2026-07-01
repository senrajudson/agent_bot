"""Integration tests for OutboxDispatcher with PostgresOutboxStore and fake consumer.

Covers D19 scenarios from the Prompt 6 specification.

These tests use a local FakeConsumer (not a production consumer) and only
exercise the dispatcher's claim / handle / mark_dispatched / mark_retry /
move_to_dlq cycle against the real Postgres schema.
"""
from __future__ import annotations

import json

import asyncpg
import pytest

from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxEvent,
    OutboxDispatcher,
    PostgresOutboxStore,
)
from tests.integration.edd.conftest import (
    count_rows,
    fetch_all,
    fetch_one,
    insert_outbox_event,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Local fake consumer
# ---------------------------------------------------------------------------


class FakeConsumer:
    """Records handled events and optionally raises for specific event_ids."""

    def __init__(self) -> None:
        self.handled: list[OutboxEvent] = []
        self._raise_on: dict[str, BaseException] = {}

    def set_raise(self, event_id: str, exc: BaseException) -> None:
        self._raise_on[event_id] = exc

    async def handle(self, event: OutboxEvent) -> None:
        self.handled.append(event)
        if event.event_id in self._raise_on:
            raise self._raise_on[event.event_id]


# ---------------------------------------------------------------------------
# D19 — empty batch
# ---------------------------------------------------------------------------


async def test_empty_batch_returns_zero_counters(
    pg_pool: asyncpg.Pool,
) -> None:
    store = PostgresOutboxStore(pool=pg_pool)
    consumer = FakeConsumer()
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name="test-dispatcher",
    )

    result = await dispatcher.dispatch_once()
    assert result.claimed_count == 0
    assert result.processed_count == 0
    assert result.already_processed_count == 0
    assert result.dispatched_count == 0
    assert result.retry_count == 0
    assert result.dlq_count == 0
    assert consumer.handled == []


# ---------------------------------------------------------------------------
# D19 — success
# ---------------------------------------------------------------------------


async def test_success_marks_dispatched_and_inserts_processed(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    consumer = FakeConsumer()
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name="test-dispatcher",
    )

    result = await dispatcher.dispatch_once()
    assert result.claimed_count == 1
    assert result.processed_count == 1
    assert result.dispatched_count == 1

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "dispatched"

    assert len(consumer.handled) == 1
    n = await count_rows(
        pg_pool,
        "processed_events",
        consumer_name="test-dispatcher",
        event_id=consumer.handled[0].event_id,
    )
    assert n == 1


# ---------------------------------------------------------------------------
# D19 — consumer receives correct payload
# ---------------------------------------------------------------------------


async def test_consumer_called_with_correct_event_payload(
    pg_pool: asyncpg.Pool,
) -> None:
    payload = {"foo": "bar", "n": 42}
    await insert_outbox_event(
        pg_pool,
        status="pending",
        event_payload=json.dumps(payload),
    )

    store = PostgresOutboxStore(pool=pg_pool)
    consumer = FakeConsumer()
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name="test-dispatcher",
    )

    await dispatcher.dispatch_once()

    assert len(consumer.handled) == 1
    assert consumer.handled[0].event_payload == payload


# ---------------------------------------------------------------------------
# D19 — retry on retryable failure
# ---------------------------------------------------------------------------


async def test_retryable_failure_marks_pending_with_incremented_attempts(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool, status="pending", attempts=0, max_attempts=3
    )
    store = PostgresOutboxStore(pool=pg_pool)
    consumer = FakeConsumer()
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name="test-dispatcher",
    )

    # Set up consumer to raise for the only event
    # We need to know the event_id before claim_batch; insert already created one
    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    consumer.set_raise(row["event_id"], ValueError("retryable"))

    result = await dispatcher.dispatch_once()
    assert result.claimed_count == 1
    assert result.retry_count == 1
    assert result.dlq_count == 0
    assert result.processed_count == 0

    row_after = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row_after is not None
    assert row_after["status"] == "pending"
    assert row_after["attempts"] == 1
    assert row_after["last_error_class"] == "ValueError"


# ---------------------------------------------------------------------------
# D19 — DLQ on terminal failure
# ---------------------------------------------------------------------------


async def test_terminal_failure_moves_to_dlq(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool, status="pending", attempts=2, max_attempts=3
    )
    store = PostgresOutboxStore(pool=pg_pool)
    consumer = FakeConsumer()
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name="test-dispatcher",
    )

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    consumer.set_raise(row["event_id"], ValueError("terminal"))

    result = await dispatcher.dispatch_once()
    assert result.dlq_count == 1
    assert result.retry_count == 0

    row_after = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row_after is not None
    assert row_after["status"] == "dead_letter"
    assert row_after["attempts"] == 3
    assert row_after["dead_lettered_at"] is not None

    all_dlq = await fetch_all(pg_pool, "outbox_dlq")
    matching = [r for r in all_dlq if r["outbox_id"] == oid]
    assert len(matching) == 1
    assert matching[0]["final_error_class"] == "ValueError"


# ---------------------------------------------------------------------------
# D19 — already processed
# ---------------------------------------------------------------------------


async def test_already_processed_skips_consumer(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    consumer = FakeConsumer()
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name="test-dispatcher",
        worker_id="w-pre",
    )

    # First dispatch — succeeds and creates processed_events row
    result1 = await dispatcher.dispatch_once()
    assert result1.processed_count == 1

    # Manually reset outbox to pending to test already-processed path
    # (in production this would not happen; we simulate it)
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE outbox_events SET status = 'pending', "
            "locked_by = NULL, locked_until = NULL, "
            "dispatched_at = NULL "
            "WHERE outbox_id = $1",
            oid,
        )

    # Second dispatch — is_processed returns true, consumer not called
    consumer2 = FakeConsumer()
    dispatcher2 = OutboxDispatcher(
        store=store,
        consumer=consumer2,
        consumer_name="test-dispatcher",
        worker_id="w-post",
    )
    result2 = await dispatcher2.dispatch_once()
    assert result2.already_processed_count == 1
    assert result2.processed_count == 0
    assert result2.dispatched_count == 1
    assert consumer2.handled == []
