"""E2E tests for the Event-Driven Design (EDD) flow.

Validates the full architecture:
- Test 1 — Happy path: /chat → Event Store → Outbox → dispatcher → handler real → processed_events
- Test 2 — DLQ + recovery: outbox → dispatch fail → DLQ → dry-run → execute → audit → reprocess → idempotency

Requires real Postgres (EVENT_STORE_POSTGRES_DSN).
Redis is NOT required — InMemoryConversationSaver replaces it.
LLM is mocked — no external calls.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from httpx import ASGITransport, AsyncClient

from app.agent.router import RouterOutput
from app.infrastructure.outbox.event_type_router_consumer import (
    EventTypeRouterConsumer,
)
from app.infrastructure.outbox.handlers.conversation_memory_save_handler import (
    ConversationMemorySaveOutboxHandler,
)
from app.infrastructure.outbox.logging_consumer import LoggingOutboxConsumer
from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxDispatcher,
    OutboxEvent,
    PostgresOutboxStore,
)

from tests.integration.edd.conftest import (
    InMemoryConversationSaver,
    count_rows,
    fetch_all,
    fetch_one,
    insert_dead_letter_event,
)

pytestmark = pytest.mark.integration

CONSUMER_NAME = "outbox-conversation-memory-save-v1"

# Ensure scripts are importable for recovery tests
_SCRIPTS_PATH = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS_PATH not in sys.path:
    sys.path.insert(0, _SCRIPTS_PATH)


# ---------------------------------------------------------------------------
# Fake consumers for controlled failure / success
# ---------------------------------------------------------------------------


class FakeFailingConsumer:
    """Always raises RuntimeError — used to force DLQ."""

    def __init__(self) -> None:
        self.handled: list[OutboxEvent] = []

    async def handle(self, event: OutboxEvent) -> None:
        self.handled.append(event)
        msg = f"synthetic failure for event_id={event.event_id}"
        raise RuntimeError(msg)


class FakeSuccessConsumer:
    """Records handled events without failing."""

    def __init__(self) -> None:
        self.handled: list[OutboxEvent] = []

    async def handle(self, event: OutboxEvent) -> None:
        self.handled.append(event)


# ===========================================================================
# Test 1 — Happy path: /chat → Event Store → Outbox → dispatch → processed
# ===========================================================================


class TestHappyPath:

    async def test_chat_publishes_event_and_dispatches_memory_save(
        self,
        pg_pool: asyncpg.Pool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Prova /chat real → Event Store → Outbox → dispatch_once
        → handler real (ConversationMemorySaveOutboxHandler)
        → processed_events → outbox.status='dispatched' → DLQ vazio."""
        # ── 1. Configurar settings EDD ──────────────────────────────
        monkeypatch.setattr(
            "app.core.config.settings.EVENT_DRIVEN_ENABLED", True
        )
        monkeypatch.setattr(
            "app.core.config.settings.EVENT_STORE_BACKEND",
            "transactional_postgres",
        )

        # ── 2. Montar app + AsyncClient (sem lifespan) ─────────────
        with patch(
            "app.observability.phoenix.setup_phoenix_tracing"
        ):
            from app.main import app as _app

        _app.state.postgres_pool = pg_pool
        try:
            # ── 3. Mockar LLM/router/OCR (async — saga faz await) ──
            async def _mock_route(**kw: Any) -> RouterOutput:
                return RouterOutput(rota="conversa_comum")

            async def _mock_general_agent(**kw: Any) -> dict:
                return {"output": "synthetic assistant message", "messages": [], "error": None}

            async def _mock_ocr(images: Any) -> list:
                return []

            monkeypatch.setattr(
                "app.agent.orchestrator.route_message",
                _mock_route,
            )
            monkeypatch.setattr(
                "app.agent.orchestrator.run_general_agent",
                _mock_general_agent,
            )
            monkeypatch.setattr(
                "app.agent.orchestrator.run_ocr_for_images",
                _mock_ocr,
            )

            # ── 4. POST /chat (via ASGITransport = mesmo event loop)
            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                "/chat",
                json={
                    "message": "synthetic user message",
                    "user_id": "test-conversation-e2e",
                },
            )
            assert (
                response.status_code == 200
            ), f"Expected 200, got {response.status_code}: {response.text}"
            body = response.json()
            assert body["ok"] is True, (
                f"Response ok=False. Full response: {body}"
            )

            # ── 6. Verificar Event Store ────────────────────────────
            es_rows = await fetch_all(pg_pool, "event_store_events")
            cms_events = [
                r
                for r in es_rows
                if r["event_type"] == "ConversationMemorySaveRequested"
            ]
            assert len(cms_events) >= 1, (
                "ConversationMemorySaveRequested not found in event_store_events"
            )
            assert cms_events[0][
                "stream_id"
            ] == "conversation:test-conversation-e2e"
            assert (
                cms_events[0]["conversation_id"]
                == "test-conversation-e2e"
            )

            # ── 7. Verificar Outbox ─────────────────────────────────
            ob_rows = await fetch_all(pg_pool, "outbox_events")
            cms_outbox = [
                r
                for r in ob_rows
                if r["event_type"] == "ConversationMemorySaveRequested"
            ]
            assert len(cms_outbox) >= 1, (
                "ConversationMemorySaveRequested not found in outbox_events"
            )
            outbox_id = cms_outbox[0]["outbox_id"]
            event_id = cms_outbox[0]["event_id"]
            assert cms_outbox[0]["status"] == "pending"
            assert (
                cms_outbox[0]["aggregate_id"] == "test-conversation-e2e"
            )

            # ── 8. Construir handler real + fake saver ──────────────
            fake_saver = InMemoryConversationSaver()
            handler = ConversationMemorySaveOutboxHandler(saver=fake_saver)
            consumer = EventTypeRouterConsumer(
                handlers={
                    "ConversationMemorySaveRequested": handler,
                },
                fallback=LoggingOutboxConsumer("e2e-fallback"),
            )
            store = PostgresOutboxStore(pool=pg_pool)
            dispatcher = OutboxDispatcher(
                store=store,
                consumer=consumer,
                consumer_name=CONSUMER_NAME,
            )

            # ── 9. Rodar dispatch_once ──────────────────────────────
            result = await dispatcher.dispatch_once()
            assert result.claimed_count >= 1, "No events claimed"
            assert result.processed_count >= 1, "No events processed"
            assert result.dispatched_count >= 1, "No events dispatched"
            assert result.dlq_count == 0, "Unexpected DLQ"
            assert result.retry_count == 0, "Unexpected retry"

            # ── 10. Verificar processed_events ──────────────────────
            n_processed = await count_rows(
                pg_pool,
                "processed_events",
                consumer_name=CONSUMER_NAME,
                event_id=event_id,
            )
            assert n_processed == 1, (
                f"processed_events count expected 1, got {n_processed}"
            )

            # ── 11. Verificar outbox dispatchado ────────────────────
            outbox_row = await fetch_one(
                pg_pool, "outbox_events", outbox_id=outbox_id
            )
            assert outbox_row is not None, "outbox row not found"
            assert outbox_row["status"] == "dispatched"

            # ── 12. Verificar fake saver ────────────────────────────
            assert len(fake_saver.turns) >= 1, "Saver was not called"
            turn = fake_saver.turns[0]
            assert turn["conversation_id"] == "test-conversation-e2e"
            assert turn["user_message"] == "synthetic user message"
            assert turn["assistant_message"] == "synthetic assistant message"

            # ── 13. Verificar DLQ vazio ─────────────────────────────
            dlq_n = await count_rows(
                pg_pool, "outbox_dlq", outbox_id=outbox_id
            )
            assert dlq_n == 0, f"Expected empty DLQ, found {dlq_n} rows"

        finally:
            # ── Cleanup: remove pool do state ───────────────────────
            if hasattr(_app.state, "postgres_pool"):
                del _app.state.postgres_pool


# ===========================================================================
# Test 2 — DLQ + recovery: outbox → dispatch fail → DLQ → dry-run → execute
#              → audit → pending → dispatch success → processed → idemp.
# ===========================================================================


class TestDlqRecovery:

    async def test_dead_letter_recovery_execute_and_reprocess(
        self,
        pg_pool: asyncpg.Pool,
        event_store_dsn: str,
        applied_sqls: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Prova DLQ real → recovery dry-run → recovery execute → audit
        → requeue → re-dispatch → idempotência."""
        import recover_outbox_event  # noqa: E402

        AGGREGATE_ID = f"conv-e2e-{uuid.uuid4().hex[:8]}"
        RECOVERY_TEST_DSN = "postgresql://u:p@127.0.0.1:5432/events"

        # ── 1. Inserir evento dead-letter-candidate ────────────────
        outbox_id, event_id = await insert_dead_letter_event(
            pg_pool,
            event_type="ConversationMemorySaveRequested",
            status="pending",
            attempts=2,
            max_attempts=3,
            aggregate_id=AGGREGATE_ID,
            event_payload={
                "user_message": "synthetic",
                "assistant_message": "synthetic",
            },
            with_dlq_snapshot=False,  # dispatch_once criará
        )

        # ── 2. Construir dispatcher com consumer falho ──────────────
        failing_consumer = FakeFailingConsumer()
        consumer_router = EventTypeRouterConsumer(
            handlers={
                "ConversationMemorySaveRequested": failing_consumer,
            },
            fallback=LoggingOutboxConsumer("e2e-dlq-fallback"),
        )
        store = PostgresOutboxStore(pool=pg_pool)
        dispatcher = OutboxDispatcher(
            store=store,
            consumer=consumer_router,
            consumer_name=CONSUMER_NAME,
        )

        # ── 3. Dispatch → DLQ (1 rodada, attempts 3 >= max 3) ──────
        result = await dispatcher.dispatch_once()
        assert result.claimed_count == 1, (
            f"Expected 1 claimed, got {result.claimed_count}"
        )
        assert result.dlq_count == 1, (
            f"Expected 1 DLQ, got {result.dlq_count}"
        )
        assert result.processed_count == 0, "Should not have processed"
        assert result.retry_count == 0, "Should not have retried"

        # ── 4. Verificar outbox.status = dead_letter ────────────────
        outbox_row = await fetch_one(
            pg_pool, "outbox_events", outbox_id=outbox_id
        )
        assert outbox_row is not None
        assert outbox_row["status"] == "dead_letter"
        assert outbox_row["attempts"] == 3
        assert outbox_row["dead_lettered_at"] is not None

        # ── 5. Verificar outbox_dlq ─────────────────────────────────
        dlq_row = await fetch_one(
            pg_pool, "outbox_dlq", outbox_id=outbox_id
        )
        assert dlq_row is not None, "DLQ snapshot missing"
        assert str(dlq_row["event_id"]) == event_id
        assert dlq_row["final_error_class"] == "RuntimeError"
        assert dlq_row["attempts"] == 3
        assert dlq_row["max_attempts"] == 3

        # ── 6. Recovery dry-run in-process ──────────────────────────
        args_dry = recover_outbox_event._parse_args(
            [
                "--outbox-id",
                str(outbox_id),
                "--ticket",
                "T-E2E-RECOVERY",
            ]
        )
        rd = await recover_outbox_event._check_eligibility(
            pg_pool,
            outbox_id=outbox_id,
            consumer_name=CONSUMER_NAME,
            ticket_or_reason="T-E2E-RECOVERY",
        )
        assert rd["eligible"] is True, (
            f"Expected eligible, got reason_code={rd.get('reason_code')}"
        )
        assert rd["status"] == "dead_letter"
        assert rd["attempts"] == 3
        assert rd["max_attempts"] == 3

        # ── 7. Recovery execute in-process ──────────────────────────
        args_exec = recover_outbox_event._parse_args(
            [
                "--outbox-id",
                str(outbox_id),
                "--ticket",
                "T-E2E-RECOVERY",
                "--execute",
                "--yes-i-confirm-recovery",
            ]
        )
        monkeypatch.setenv("EVENT_STORE_POSTGRES_DSN", RECOVERY_TEST_DSN)
        # Cria pool separado para recovery (execute_recovery fecha o pool)
        recovery_pool = await asyncpg.create_pool(
            event_store_dsn,
            min_size=1,
            max_size=1,
            server_settings={"search_path": applied_sqls},
        )
        with patch(
            "asyncpg.create_pool", new_callable=AsyncMock
        ) as mock_pool:

            async def _fake_create_pool(*a: Any, **kw: Any) -> asyncpg.Pool:
                return recovery_pool

            mock_pool.side_effect = _fake_create_pool
            exit_code = await recover_outbox_event._execute_recovery(
                RECOVERY_TEST_DSN, args_exec
            )

        assert exit_code == 0, (
            f"Recovery execute failed with code {exit_code}"
        )

        # ── 8. Verificar outbox_recovery_audit ──────────────────────
        audit_row = await fetch_one(
            pg_pool, "outbox_recovery_audit", outbox_id=outbox_id
        )
        assert audit_row is not None, "Audit row missing"
        assert audit_row["operation"] == "recovery_execute"
        assert audit_row["command_source"] == "cli"
        assert audit_row["previous_status"] == "dead_letter"
        assert audit_row["new_status"] == "pending"
        assert audit_row["new_attempts"] == 0
        uuid.UUID(str(audit_row["operation_id"]))  # valid UUID

        # ── 9. Audit metadata sem PII ───────────────────────────────
        md = audit_row["metadata"]
        if isinstance(md, str):
            md = json.loads(md)
        forbidden_keys = {
            "event_payload",
            "payload",
            "user_message",
            "assistant_message",
            "aggregate_id",
            "conversation_id",
            "user_id",
            "dsn",
        }
        for key in forbidden_keys:
            assert key not in md, (
                f"Audit metadata leaked forbidden key: {key!r}"
            )

        # ── 10. Verificar status pending after recovery ─────────────
        outbox_row = await fetch_one(
            pg_pool, "outbox_events", outbox_id=outbox_id
        )
        assert outbox_row is not None
        assert outbox_row["status"] == "pending"
        assert outbox_row["attempts"] == 0
        assert outbox_row["locked_by"] is None
        assert outbox_row["locked_until"] is None

        # ── 11. Verificar outbox_dlq preservado ─────────────────────
        dlq_count = await count_rows(
            pg_pool, "outbox_dlq", outbox_id=outbox_id
        )
        assert dlq_count == 1, "DLQ snapshot should be preserved"

        # ── 12. Verificar processed_events intocado ─────────────────
        proc_before = await count_rows(
            pg_pool,
            "processed_events",
            consumer_name=CONSUMER_NAME,
            event_id=event_id,
        )
        assert proc_before == 0, (
            "processed_events should be unchanged before re-dispatch"
        )

        # ── 13. Re-dispatch com consumer de sucesso ─────────────────
        success_consumer = FakeSuccessConsumer()
        consumer_success = EventTypeRouterConsumer(
            handlers={
                "ConversationMemorySaveRequested": success_consumer,
            },
            fallback=LoggingOutboxConsumer("e2e-reprocess-fallback"),
        )
        dispatcher2 = OutboxDispatcher(
            store=PostgresOutboxStore(pool=pg_pool),
            consumer=consumer_success,
            consumer_name=CONSUMER_NAME,
        )
        result2 = await dispatcher2.dispatch_once()
        assert result2.processed_count == 1, (
            f"Expected 1 processed after recovery, "
            f"got claimed={result2.claimed_count} "
            f"processed={result2.processed_count}"
        )
        assert result2.dispatched_count == 1

        # ── 14. Verificar outbox dispatched ─────────────────────────
        outbox_row = await fetch_one(
            pg_pool, "outbox_events", outbox_id=outbox_id
        )
        assert outbox_row is not None
        assert outbox_row["status"] == "dispatched"

        # ── 15. Verificar processed_events registrado ───────────────
        n_processed = await count_rows(
            pg_pool,
            "processed_events",
            consumer_name=CONSUMER_NAME,
            event_id=event_id,
        )
        assert n_processed == 1

        # ── 16. Idempotência: reset outbox → re-dispatch → skip ────
        async with pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE outbox_events SET status = 'pending', "
                "locked_by = NULL, locked_until = NULL, "
                "dispatched_at = NULL WHERE outbox_id = $1",
                outbox_id,
            )
        consumer_idem = EventTypeRouterConsumer(
            handlers={
                "ConversationMemorySaveRequested": FakeSuccessConsumer(),
            },
            fallback=LoggingOutboxConsumer("e2e-idem-fallback"),
        )
        dispatcher3 = OutboxDispatcher(
            store=PostgresOutboxStore(pool=pg_pool),
            consumer=consumer_idem,
            consumer_name=CONSUMER_NAME,
        )
        result3 = await dispatcher3.dispatch_once()
        assert result3.already_processed_count == 1, (
            f"Expected already_processed=1, "
            f"got already_processed={result3.already_processed_count}"
        )
        assert result3.processed_count == 0

        # ── 17. outbox_dlq ainda preservado ─────────────────────────
        dlq_count2 = await count_rows(
            pg_pool, "outbox_dlq", outbox_id=outbox_id
        )
        assert dlq_count2 == 1, (
            "DLQ snapshot should still be preserved after idempotent dispatch"
        )
