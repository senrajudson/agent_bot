from __future__ import annotations

import logging

import asyncpg
import pytest

from app.infrastructure.outbox.logging_consumer import LoggingOutboxConsumer
from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxEvent,
    OutboxDispatcher,
    PostgresOutboxStore,
)
from tests.integration.edd.conftest import (
    assert_outbox_status,
    count_rows,
    fetch_one,
    insert_outbox_event,
)

pytestmark = pytest.mark.integration


class RaisingConsumer:
    def __init__(self) -> None:
        self.handled: list[OutboxEvent] = []

    async def handle(self, event: OutboxEvent) -> None:
        self.handled.append(event)
        msg = f"simulated consumer failure for {event.event_id}"
        raise ValueError(msg)


class TestLoggingConsumerIntegration:
    async def test_one_event_dispatched(self, pg_pool: asyncpg.Pool) -> None:
        oid = await insert_outbox_event(pg_pool, status="pending")
        store = PostgresOutboxStore(pool=pg_pool)
        consumer = LoggingOutboxConsumer("test-int")
        dispatcher = OutboxDispatcher(
            store=store,
            consumer=consumer,
            consumer_name="test-int-dispatcher",
        )
        result = await dispatcher.dispatch_once()
        assert result.claimed_count == 1
        assert result.processed_count == 1
        assert result.dispatched_count == 1
        assert result.retry_count == 0
        assert result.dlq_count == 0
        await assert_outbox_status(pg_pool, oid, "dispatched")
        n = await count_rows(
            pg_pool,
            "processed_events",
            consumer_name="test-int-dispatcher",
        )
        assert n == 1

    async def test_two_events_both_dispatched(self, pg_pool: asyncpg.Pool) -> None:
        oid_a = await insert_outbox_event(pg_pool, status="pending")
        oid_b = await insert_outbox_event(pg_pool, status="pending")
        store = PostgresOutboxStore(pool=pg_pool)
        consumer = LoggingOutboxConsumer("test-int-2")
        dispatcher = OutboxDispatcher(
            store=store,
            consumer=consumer,
            consumer_name="test-int-dispatcher-2",
            batch_size=10,
        )
        result = await dispatcher.dispatch_once()
        assert result.claimed_count == 2
        assert result.processed_count == 2
        assert result.dispatched_count == 2
        await assert_outbox_status(pg_pool, oid_a, "dispatched")
        await assert_outbox_status(pg_pool, oid_b, "dispatched")
        n = await count_rows(
            pg_pool,
            "processed_events",
            consumer_name="test-int-dispatcher-2",
        )
        assert n == 2

    async def test_rerun_is_idempotent(self, pg_pool: asyncpg.Pool) -> None:
        oid = await insert_outbox_event(pg_pool, status="pending")
        store = PostgresOutboxStore(pool=pg_pool)
        consumer = LoggingOutboxConsumer("test-int-3")
        dispatcher = OutboxDispatcher(
            store=store,
            consumer=consumer,
            consumer_name="test-int-dispatcher-3",
        )
        result1 = await dispatcher.dispatch_once()
        assert result1.processed_count == 1

        async with pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE outbox_events SET status = 'pending', "
                "locked_by = NULL, locked_until = NULL, "
                "dispatched_at = NULL WHERE outbox_id = $1",
                oid,
            )
        dispatcher2 = OutboxDispatcher(
            store=store,
            consumer=LoggingOutboxConsumer("test-int-3"),
            consumer_name="test-int-dispatcher-3",
            worker_id="w-rerun",
        )
        result2 = await dispatcher2.dispatch_once()
        assert result2.already_processed_count == 1
        assert result2.processed_count == 0
        assert result2.dispatched_count == 1
        n = await count_rows(
            pg_pool,
            "processed_events",
            consumer_name="test-int-dispatcher-3",
        )
        assert n == 1

    async def test_consumer_failure_triggers_retry(self, pg_pool: asyncpg.Pool) -> None:
        oid = await insert_outbox_event(
            pg_pool, status="pending", attempts=0, max_attempts=3
        )
        row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
        assert row is not None
        store = PostgresOutboxStore(pool=pg_pool)
        consumer = RaisingConsumer()
        dispatcher = OutboxDispatcher(
            store=store,
            consumer=consumer,
            consumer_name="test-int-fail",
        )
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
