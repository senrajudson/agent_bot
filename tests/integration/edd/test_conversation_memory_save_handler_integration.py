"""Integration test: retry with real ConversationMemorySaveOutboxHandler against Postgres."""
from __future__ import annotations

from typing import Any, Mapping

import asyncpg
import pytest

from app.infrastructure.outbox.event_type_router_consumer import (
    EventTypeRouterConsumer,
)
from app.infrastructure.outbox.handlers.conversation_memory_save_handler import (
    ConversationMemorySaveOutboxHandler,
)
from app.infrastructure.outbox.logging_consumer import LoggingOutboxConsumer
from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxDispatcher,
    PostgresOutboxStore,
)
from tests.integration.edd.conftest import (
    count_rows,
    fetch_one,
    insert_outbox_event,
)

import json

pytestmark = pytest.mark.integration

CONSUMER_NAME = "outbox-conversation-memory-save-v1"

USER_SECRET_SENTINEL = "USER_SECRET_SENTINEL_DO_NOT_LEAK"
ASSISTANT_SECRET_SENTINEL = "ASSISTANT_SECRET_SENTINEL_DO_NOT_LEAK"


class FakeFailingConversationMemorySaver:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def save(self, payload: Mapping[str, Any]) -> None:
        raise self._exc


async def test_retry_with_real_handler_against_postgres(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool,
        event_type="ConversationMemorySaveRequested",
        aggregate_id="user-cms-1",
        event_payload=json.dumps({
            "user_message": "u",
            "assistant_message": "a",
            "user_id": "user-cms-1",
        }),
        attempts=0,
        max_attempts=3,
    )

    store = PostgresOutboxStore(pool=pg_pool)
    saver = FakeFailingConversationMemorySaver(
        RuntimeError("simulated redis failure")
    )
    handler = ConversationMemorySaveOutboxHandler(saver=saver)
    fallback = LoggingOutboxConsumer("test-fallback-cms-retry")
    consumer = EventTypeRouterConsumer(
        handlers={"ConversationMemorySaveRequested": handler},
        fallback=fallback,
    )
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name=CONSUMER_NAME,
    )

    result = await dispatcher.dispatch_once()

    assert result.claimed_count == 1
    assert result.processed_count == 0
    assert result.retry_count == 1
    assert result.dlq_count == 0
    assert result.dispatched_count == 0

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["last_error_class"] == "RuntimeError"
    assert row["last_error"] is not None
    assert "simulated redis failure" in row["last_error"]
    assert row["locked_by"] is None
    assert row["locked_until"] is None

    n_processed = await count_rows(
        pg_pool,
        "processed_events",
        outbox_id=oid,
    )
    assert n_processed == 0

    dlq_row = await fetch_one(pg_pool, "outbox_dlq", outbox_id=oid)
    assert dlq_row is None


async def test_retry_sanitizes_last_error_against_sentinels(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool,
        event_type="ConversationMemorySaveRequested",
        aggregate_id="user-cms-sanitize-retry",
        event_payload=json.dumps({
            "user_message": USER_SECRET_SENTINEL,
            "assistant_message": ASSISTANT_SECRET_SENTINEL,
            "user_id": "user-cms-sanitize-retry",
        }),
        attempts=0,
        max_attempts=3,
    )

    store = PostgresOutboxStore(pool=pg_pool)
    saver = FakeFailingConversationMemorySaver(
        RuntimeError(
            f"simulated failure: user_message={USER_SECRET_SENTINEL} "
            f"assistant_message={ASSISTANT_SECRET_SENTINEL}"
        )
    )
    handler = ConversationMemorySaveOutboxHandler(saver=saver)
    fallback = LoggingOutboxConsumer("test-fallback-cms-sanitize-retry")
    consumer = EventTypeRouterConsumer(
        handlers={"ConversationMemorySaveRequested": handler},
        fallback=fallback,
    )
    dispatcher = OutboxDispatcher(
        store=store,
        consumer=consumer,
        consumer_name=CONSUMER_NAME,
    )

    result = await dispatcher.dispatch_once()

    assert result.claimed_count == 1
    assert result.retry_count == 1
    assert result.dlq_count == 0

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["last_error_class"] == "RuntimeError"
    assert row["last_error"] is not None
    assert USER_SECRET_SENTINEL not in row["last_error"]
    assert ASSISTANT_SECRET_SENTINEL not in row["last_error"]
    assert "<REDACTED>" in row["last_error"]

    n_processed = await count_rows(
        pg_pool,
        "processed_events",
        outbox_id=oid,
    )
    assert n_processed == 0

    dlq_row = await fetch_one(pg_pool, "outbox_dlq", outbox_id=oid)
    assert dlq_row is None
