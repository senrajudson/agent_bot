"""Integration tests for PostgresOutboxStore against real Postgres.

Covers D18 (claim/mark_dispatched/mark_retry/move_to_dlq),
D20 (SKIP LOCKED concurrent),
D21 (lock expired reprocessable),
D22 (ON CONFLICT DO NOTHING idempotency).

These tests do NOT touch /chat, the orchestrator, the Saga, the EventPublisher,
or the factory. They only validate the isolated outbox store against the
real schema.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxEvent,
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
# D18 — claim_batch
# ---------------------------------------------------------------------------


async def test_claim_batch_empty_returns_empty_list(
    pg_pool: asyncpg.Pool,
) -> None:
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    assert events == []


async def test_claim_batch_selects_pending_available(
    pg_pool: asyncpg.Pool,
) -> None:
    now = datetime.now(timezone.utc)
    oid_a = await insert_outbox_event(
        pg_pool, status="pending", available_at=now - timedelta(seconds=10)
    )
    oid_b = await insert_outbox_event(
        pg_pool, status="pending", available_at=now - timedelta(seconds=5)
    )

    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    assert len(events) == 2
    ids = {e.outbox_id for e in events}
    assert ids == {oid_a, oid_b}


async def test_claim_batch_ignores_pending_with_future_available_at(
    pg_pool: asyncpg.Pool,
) -> None:
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    await insert_outbox_event(pg_pool, status="pending", available_at=future)

    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    assert events == []


async def test_claim_batch_includes_expired_locked(
    pg_pool: asyncpg.Pool,
) -> None:
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    oid = await insert_outbox_event(
        pg_pool,
        status="locked",
        locked_by="w-old",
        locked_until=past,
    )

    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    assert len(events) == 1
    assert events[0].outbox_id == oid


async def test_claim_batch_ignores_active_locked(
    pg_pool: asyncpg.Pool,
) -> None:
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    await insert_outbox_event(
        pg_pool,
        status="locked",
        locked_by="w-active",
        locked_until=future,
    )

    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    assert events == []


async def test_claim_batch_sets_status_locked_with_worker_id_and_lock_ttl(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")

    store = PostgresOutboxStore(pool=pg_pool)
    before = datetime.now(timezone.utc)
    events = await store.claim_batch(
        worker_id="w-x", batch_size=10, lock_ttl_seconds=30
    )
    after = datetime.now(timezone.utc)

    assert len(events) == 1
    assert events[0].status == "locked"
    assert events[0].locked_by == "w-x"
    assert events[0].locked_until is not None
    # locked_until should be between now+30s (with some margin)
    expected_min = before + timedelta(seconds=30) - timedelta(seconds=2)
    expected_max = after + timedelta(seconds=30) + timedelta(seconds=2)
    assert expected_min <= events[0].locked_until <= expected_max, (
        f"locked_until={events[0].locked_until} not in "
        f"[{expected_min}, {expected_max}]"
    )

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "locked"
    assert row["locked_by"] == "w-x"


async def test_claim_batch_orders_by_available_at_asc(
    pg_pool: asyncpg.Pool,
) -> None:
    now = datetime.now(timezone.utc)
    # Insert 3 eligible events at different times (all <= NOW)
    oid_late = await insert_outbox_event(
        pg_pool, status="pending", available_at=now - timedelta(minutes=1)
    )
    oid_early = await insert_outbox_event(
        pg_pool, status="pending", available_at=now - timedelta(minutes=10)
    )
    oid_mid = await insert_outbox_event(
        pg_pool, status="pending", available_at=now - timedelta(minutes=5)
    )

    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    # All 3 should be returned, ordered by available_at ASC
    assert len(events) == 3
    assert events[0].outbox_id == oid_early  # -10min
    assert events[1].outbox_id == oid_mid    # -5min
    assert events[2].outbox_id == oid_late   # -1min


async def test_claim_batch_respects_batch_size_limit(
    pg_pool: asyncpg.Pool,
) -> None:
    for _ in range(5):
        await insert_outbox_event(pg_pool, status="pending")

    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=2, lock_ttl_seconds=30
    )
    assert len(events) == 2


# ---------------------------------------------------------------------------
# D18 — is_processed
# ---------------------------------------------------------------------------


async def test_is_processed_false_when_no_row(pg_pool: asyncpg.Pool) -> None:
    store = PostgresOutboxStore(pool=pg_pool)
    result = await store.is_processed(consumer_name="c1", event_id="00000000-0000-0000-0000-000000000000")
    assert result is False


async def test_is_processed_true_when_row_exists(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.mark_dispatched(event=events[0], consumer_name="c1")

    result = await store.is_processed(consumer_name="c1", event_id=events[0].event_id)
    assert result is True


# ---------------------------------------------------------------------------
# D18 — mark_dispatched
# ---------------------------------------------------------------------------


async def test_mark_dispatched_inserts_processed_events(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.mark_dispatched(event=events[0], consumer_name="c1")

    n = await count_rows(
        pg_pool,
        "processed_events",
        consumer_name="c1",
        event_id=events[0].event_id,
    )
    assert n == 1


async def test_mark_dispatched_sets_outbox_status_dispatched(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.mark_dispatched(event=events[0], consumer_name="c1")

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "dispatched"
    assert row["dispatched_at"] is not None
    assert row["locked_by"] is None
    assert row["locked_until"] is None


async def test_mark_dispatched_is_idempotent_on_consumer_event_id(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    # Reclaim not possible because status moved to dispatched
    # but is_processed should already be true → simulate
    # by calling mark_dispatched twice on the same OutboxEvent object
    # we keep the first event object; status doesn't matter for mark_dispatched
    await store.mark_dispatched(event=events[0], consumer_name="c1")
    await store.mark_dispatched(event=events[0], consumer_name="c1")

    n = await count_rows(
        pg_pool,
        "processed_events",
        consumer_name="c1",
        event_id=events[0].event_id,
    )
    assert n == 1

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "dispatched"


# ---------------------------------------------------------------------------
# D18 — mark_retry
# ---------------------------------------------------------------------------


async def test_mark_retry_increments_attempts(pg_pool: asyncpg.Pool) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending", attempts=0)
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.mark_retry(
        event=events[0], error=ValueError("boom"), delay_seconds=1.0
    )

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["attempts"] == 1


async def test_mark_retry_resets_status_to_pending(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.mark_retry(
        event=events[0], error=ValueError("x"), delay_seconds=1.0
    )

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "pending"


async def test_mark_retry_schedules_available_at_in_future(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )

    before = datetime.now(timezone.utc)
    await store.mark_retry(
        event=events[0], error=ValueError("x"), delay_seconds=5.0
    )
    after = datetime.now(timezone.utc)

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    available_at = row["available_at"]
    # available_at should be in the future
    assert available_at > before
    assert available_at >= before + timedelta(seconds=5) - timedelta(seconds=1)
    assert available_at <= after + timedelta(seconds=5) + timedelta(seconds=1)


async def test_mark_retry_clears_lock_fields(pg_pool: asyncpg.Pool) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.mark_retry(
        event=events[0], error=ValueError("x"), delay_seconds=1.0
    )

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["locked_by"] is None
    assert row["locked_until"] is None


async def test_mark_retry_records_last_error_and_class(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.mark_retry(
        event=events[0],
        error=ValueError("specific error message"),
        delay_seconds=1.0,
    )

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["last_error_class"] == "ValueError"
    assert row["last_error"] is not None
    assert "specific error message" in row["last_error"]


# ---------------------------------------------------------------------------
# D18 — move_to_dlq
# ---------------------------------------------------------------------------


async def test_move_to_dlq_inserts_outbox_dlq_snapshot(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool, status="pending", attempts=2, max_attempts=3
    )
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.move_to_dlq(
        event=events[0], error=ValueError("terminal")
    )

    # outbox_dlq.whitelist allows where by outbox_id
    all_dlq = await fetch_all(pg_pool, "outbox_dlq")
    matching = [r for r in all_dlq if r["outbox_id"] == oid]
    assert len(matching) == 1
    dlq_row = matching[0]
    assert dlq_row["event_id"] == events[0].event_id
    assert dlq_row["event_type"] == events[0].event_type
    assert dlq_row["attempts"] == 3
    assert dlq_row["max_attempts"] == 3


async def test_move_to_dlq_sets_outbox_status_dead_letter(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool, status="pending", attempts=2, max_attempts=3
    )
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.move_to_dlq(
        event=events[0], error=ValueError("terminal")
    )

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "dead_letter"
    assert row["dead_lettered_at"] is not None


async def test_move_to_dlq_records_final_error(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool, status="pending", attempts=2, max_attempts=3
    )
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    await store.move_to_dlq(
        event=events[0], error=ValueError("final error msg")
    )

    all_dlq = await fetch_all(pg_pool, "outbox_dlq")
    matching = [r for r in all_dlq if r["outbox_id"] == oid]
    assert len(matching) == 1
    assert matching[0]["final_error_class"] == "ValueError"
    assert "final error msg" in matching[0]["final_error"]


# ---------------------------------------------------------------------------
# D20 — concurrent SKIP LOCKED
# ---------------------------------------------------------------------------


async def test_claim_batch_skip_locked_concurrent_workers(
    pg_pool: asyncpg.Pool,
) -> None:
    inserted_ids = set()
    for _ in range(4):
        oid = await insert_outbox_event(pg_pool, status="pending")
        inserted_ids.add(oid)

    store_a = PostgresOutboxStore(pool=pg_pool)
    store_b = PostgresOutboxStore(pool=pg_pool)

    results = await asyncio.gather(
        store_a.claim_batch(
            worker_id="w-a", batch_size=10, lock_ttl_seconds=30
        ),
        store_b.claim_batch(
            worker_id="w-b", batch_size=10, lock_ttl_seconds=30
        ),
    )

    ids_a = {e.outbox_id for e in results[0]}
    ids_b = {e.outbox_id for e in results[1]}

    assert ids_a.isdisjoint(ids_b), (
        f"SKIP LOCKED failed: {ids_a & ids_b}"
    )
    assert ids_a | ids_b == inserted_ids, (
        f"expected {inserted_ids}, got A={ids_a} B={ids_b}"
    )


# ---------------------------------------------------------------------------
# D21 — lock expired reprocessable
# ---------------------------------------------------------------------------


async def test_lock_expired_event_is_reprocessable(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)

    # Initial claim by worker A
    events_a = await store.claim_batch(
        worker_id="w-a", batch_size=10, lock_ttl_seconds=30
    )
    assert len(events_a) == 1
    assert events_a[0].outbox_id == oid
    assert events_a[0].locked_by == "w-a"

    # Force lock_until to the past
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE outbox_events SET locked_until = NOW() - INTERVAL '1 second' "
            "WHERE outbox_id = $1",
            oid,
        )

    # Reclaim with worker B
    events_b = await store.claim_batch(
        worker_id="w-b", batch_size=10, lock_ttl_seconds=30
    )
    assert len(events_b) == 1
    assert events_b[0].outbox_id == oid
    assert events_b[0].locked_by == "w-b"


# ---------------------------------------------------------------------------
# D22 — ON CONFLICT DO NOTHING idempotency
# ---------------------------------------------------------------------------


async def test_processed_events_idempotency_under_repeated_dispatch(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(pg_pool, status="pending")
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    event = events[0]

    # Call mark_dispatched twice in a row (same consumer_name, same event_id)
    await store.mark_dispatched(event=event, consumer_name="c1")
    await store.mark_dispatched(event=event, consumer_name="c1")

    n = await count_rows(
        pg_pool, "processed_events", consumer_name="c1", event_id=event.event_id
    )
    assert n == 1, "ON CONFLICT DO NOTHING should keep processed_events at 1 row"

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "dispatched"


# ---------------------------------------------------------------------------
# D23 — move_to_dlq upsert: second call must not raise UniqueViolationError
# ---------------------------------------------------------------------------


async def test_move_to_dlq_is_upsert_on_conflict(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool, status="pending", attempts=2, max_attempts=3
    )
    store = PostgresOutboxStore(pool=pg_pool)
    events = await store.claim_batch(
        worker_id="w-1", batch_size=10, lock_ttl_seconds=30
    )
    event = events[0]

    # First call: creates outbox_dlq row
    await store.move_to_dlq(event=event, error=ValueError("first error"))

    first_dlq_all = await fetch_all(pg_pool, "outbox_dlq")
    first_matching = [r for r in first_dlq_all if r["outbox_id"] == oid]
    assert len(first_matching) == 1
    first_moved_at = first_matching[0]["moved_to_dlq_at"]

    # Second call: must NOT raise UniqueViolationError
    await store.move_to_dlq(event=event, error=ValueError("second error"))

    # Assert: still 1 row in outbox_dlq
    all_dlq = await fetch_all(pg_pool, "outbox_dlq")
    matching = [r for r in all_dlq if r["outbox_id"] == oid]
    assert len(matching) == 1
    dlq_row = matching[0]

    # Assert: final error reflects the second call
    assert "second error" in dlq_row["final_error"]
    assert dlq_row["final_error_class"] == "ValueError"

    # Assert: attempts reflect the second call (2+1=3)
    assert dlq_row["attempts"] == 3
    assert dlq_row["max_attempts"] == 3

    # Assert: moved_to_dlq_at was updated (second call)
    assert dlq_row["moved_to_dlq_at"] > first_moved_at, (
        f"moved_to_dlq_at must be updated; "
        f"first={first_moved_at}, second={dlq_row['moved_to_dlq_at']}"
    )

    # Assert: original_created_at is preserved
    event_row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert event_row is not None
    assert dlq_row["original_created_at"] == event_row["created_at"], (
        f"original_created_at must be preserved; "
        f"got {dlq_row['original_created_at']}, "
        f"expected {event_row['created_at']}"
    )

    # Assert: outbox_events.status remains dead_letter
    assert event_row["status"] == "dead_letter"

    # Assert: event_payload remains in dlq
    import json
    payload = json.loads(dlq_row["event_payload"])
    assert isinstance(payload, dict)
