"""Integration test: DLQ with real ConversationMemorySaveOutboxHandler against Postgres."""
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


# NOTE: event_payload em outbox_dlq persiste snapshot integral por design
# atual do schema. final_error e last_error sao sanitizados.
# Sao politicas distintas e intencionalmente diferentes.


class FakeFailingConversationMemorySaver:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def save(self, payload: Mapping[str, Any]) -> None:
        raise self._exc


async def test_dlq_with_real_handler_against_postgres(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool,
        event_type="ConversationMemorySaveRequested",
        aggregate_id="user-cms-2",
        event_payload=json.dumps({
            "user_message": "u",
            "assistant_message": "a",
            "user_id": "user-cms-2",
        }),
        attempts=2,
        max_attempts=3,
    )

    store = PostgresOutboxStore(pool=pg_pool)
    saver = FakeFailingConversationMemorySaver(
        RuntimeError("simulated redis failure")
    )
    handler = ConversationMemorySaveOutboxHandler(saver=saver)
    fallback = LoggingOutboxConsumer("test-fallback-cms-dlq")
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

    assert result.dlq_count == 1
    assert result.processed_count == 0
    assert result.retry_count == 0

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "dead_letter"
    assert row["attempts"] == 3
    assert row["dead_lettered_at"] is not None

    dlq_row = await fetch_one(pg_pool, "outbox_dlq", outbox_id=oid)
    assert dlq_row is not None
    assert dlq_row["event_id"] == row["event_id"]
    assert dlq_row["event_type"] == "ConversationMemorySaveRequested"
    assert dlq_row["final_error_class"] == "RuntimeError"

    n_processed = await count_rows(
        pg_pool,
        "processed_events",
        outbox_id=oid,
    )
    assert n_processed == 0


async def test_dlq_sanitizes_final_error_against_sentinels(
    pg_pool: asyncpg.Pool,
) -> None:
    oid = await insert_outbox_event(
        pg_pool,
        event_type="ConversationMemorySaveRequested",
        aggregate_id="user-cms-sanitize-dlq",
        event_payload=json.dumps({
            "user_message": USER_SECRET_SENTINEL,
            "assistant_message": ASSISTANT_SECRET_SENTINEL,
            "user_id": "user-cms-sanitize-dlq",
        }),
        attempts=2,
        max_attempts=3,
    )

    store = PostgresOutboxStore(pool=pg_pool)
    saver = FakeFailingConversationMemorySaver(
        RuntimeError(
            f"terminal failure: user_message={USER_SECRET_SENTINEL} "
            f"assistant_message={ASSISTANT_SECRET_SENTINEL}"
        )
    )
    handler = ConversationMemorySaveOutboxHandler(saver=saver)
    fallback = LoggingOutboxConsumer("test-fallback-cms-sanitize-dlq")
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

    assert result.dlq_count == 1
    assert result.retry_count == 0

    row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
    assert row is not None
    assert row["status"] == "dead_letter"
    assert row["attempts"] == 3

    dlq_row = await fetch_one(pg_pool, "outbox_dlq", outbox_id=oid)
    assert dlq_row is not None
    assert dlq_row["event_id"] == row["event_id"]
    assert dlq_row["event_type"] == "ConversationMemorySaveRequested"
    assert dlq_row["final_error_class"] == "RuntimeError"
    assert USER_SECRET_SENTINEL not in dlq_row["final_error"]
    assert ASSISTANT_SECRET_SENTINEL not in dlq_row["final_error"]
    assert "<REDACTED>" in dlq_row["final_error"]

    # event_payload permanece intacto e sensivel por design do schema
    stored_payload = json.loads(dlq_row["event_payload"])
    assert stored_payload["user_message"] == USER_SECRET_SENTINEL
    assert stored_payload["assistant_message"] == ASSISTANT_SECRET_SENTINEL

    n_processed = await count_rows(
        pg_pool,
        "processed_events",
        outbox_id=oid,
    )
    assert n_processed == 0
