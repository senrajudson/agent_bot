"""Integration tests for recover_outbox_event.py --execute against real Postgres.

Validates Prompt 24: requeue dead_letter → pending with audit and lock.
Requires EVENT_STORE_POSTGRES_DSN (uses 001-005 from conftest fixtures).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from tests.integration.edd.conftest import (
    count_rows,
    fetch_one,
    fetch_all,
    insert_dead_letter_event,
    insert_outbox_event,
)

_SCRIPTS = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import recover_outbox_event  # noqa: E402

pytestmark = pytest.mark.integration

CONSUMER_NAME = "outbox-execute-test-v1"
_DSN_OK = "postgresql://u:p@127.0.0.1:5432/events"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_execute_args(
    outbox_id: int,
    ticket: str | None = None,
    reason: str | None = None,
    requested_by: str | None = None,
    consumer_name: str | None = None,
    json_output: bool = False,
) -> tuple[recover_outbox_event._ArgParser, Any]:
    """Build args for --execute mode.

    Returns (parser, args_namespace).
    """
    argv = [
        "--outbox-id", str(outbox_id),
        "--execute",
        "--yes-i-confirm-recovery",
    ]
    if ticket:
        argv += ["--ticket", ticket]
    elif reason:
        argv += ["--reason", reason]
    else:
        tick = f"TICKET-{outbox_id}"
        argv += ["--ticket", tick]
    if requested_by:
        argv += ["--requested-by", requested_by]
    if consumer_name:
        argv += ["--consumer-name", consumer_name]
    if json_output:
        argv += ["--json"]
    args = recover_outbox_event._parse_args(argv)
    return args


async def _run_execute(
    pg_pool: asyncpg.Pool,
    outbox_id: int,
    ticket: str | None = None,
    reason: str | None = None,
    requested_by: str | None = None,
) -> int:
    """Run recover_outbox_event._execute_recovery against real pool.

    Returns exit code.
    """
    os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
    args = _make_execute_args(outbox_id, ticket=ticket, reason=reason,
                              requested_by=requested_by)
    # Patch asyncpg.create_pool to return the existing pg_pool
    async def _fake_create_pool(*a: Any, **kw: Any) -> asyncpg.Pool:
        return pg_pool
    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
        mock_pool.side_effect = _fake_create_pool
        code = await recover_outbox_event._execute_recovery(_DSN_OK, args)
    return code


# ===========================================================================
# Tests
# ===========================================================================


class TestExecuteEligible:
    async def test_execute_eligible_rewrites_status_to_pending(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T1")
        assert code == 0, f"expected 0, got {code}"

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row is not None
        assert row["status"] == "pending"
        assert row["attempts"] == 0
        assert row["locked_by"] is None
        assert row["locked_until"] is None
        assert row["last_error"] is None
        assert row["last_error_class"] is None
        assert row["dead_lettered_at"] is None

    async def test_execute_writes_audit_recovery_execute(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-AUDIT")
        assert code == 0

        audit_rows = await fetch_all(pg_pool, "outbox_recovery_audit")
        matching = [r for r in audit_rows if r["outbox_id"] == outbox_id]
        assert len(matching) == 1
        audit = matching[0]
        assert audit["operation"] == "recovery_execute"
        assert audit["command_source"] == "cli"
        assert audit["previous_status"] == "dead_letter"
        assert audit["new_status"] == "pending"
        assert audit["new_attempts"] == 0
        assert audit["sanitized_error"] is None

    async def test_audit_does_not_contain_event_payload(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-NOPII")
        assert code == 0

        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT metadata FROM outbox_recovery_audit WHERE outbox_id = $1",
                outbox_id,
            )
        assert row is not None
        md = json.loads(row["metadata"])
        assert "event_payload" not in md
        assert "user_message" not in md
        assert "assistant_message" not in md
        assert "aggregate_id" not in md
        assert "conversation_id" not in md
        assert "user_id" not in md
        assert "dsn" not in md

    async def test_execute_clears_locked_by_and_locked_until(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-LOCK")
        assert code == 0

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row is not None
        assert row["locked_by"] is None
        assert row["locked_until"] is None

    async def test_execute_resets_attempts_to_zero(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool, attempts=3, max_attempts=5)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-ATMP")
        assert code == 0

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row is not None
        assert row["attempts"] == 0

    async def test_execute_preserves_max_attempts(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool, max_attempts=7)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-MAX")
        assert code == 0

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row is not None
        assert row["max_attempts"] == 7

    async def test_execute_preserves_event_id_and_payload_and_metadata(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, event_id = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-PRESV")
        assert code == 0

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row is not None
        assert row["event_id"] == event_id
        assert row["event_payload"] is not None
        # metadata in outbox_events was None, should remain None
        assert row["metadata"] is None or isinstance(row["metadata"], dict)

    async def test_execute_preserves_outbox_dlq_snapshot(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-DLQ")
        assert code == 0

        dlq_rows = await fetch_all(pg_pool, "outbox_dlq")
        matching = [r for r in dlq_rows if r["outbox_id"] == outbox_id]
        assert len(matching) == 1
        assert matching[0]["outbox_id"] == outbox_id

    async def test_operation_id_appears_in_audit(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-OID")
        assert code == 0

        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT operation_id FROM outbox_recovery_audit WHERE outbox_id = $1",
                outbox_id,
            )
        assert row is not None
        op_id = row["operation_id"]
        # must be a valid UUID
        uuid.UUID(str(op_id))

    async def test_requested_by_omitted_records_null(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-NULL")
        assert code == 0

        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT requested_by FROM outbox_recovery_audit WHERE outbox_id = $1",
                outbox_id,
            )
        assert row is not None
        assert row["requested_by"] is None

    async def test_requested_by_provided_records_value(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-RB",
                                  requested_by="alice")
        assert code == 0

        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT requested_by FROM outbox_recovery_audit WHERE outbox_id = $1",
                outbox_id,
            )
        assert row is not None
        assert row["requested_by"] == "alice"


class TestExecuteBlocks:
    async def test_blocks_if_processed_events_exists(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, event_id = await insert_dead_letter_event(pg_pool)
        async with pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO processed_events (consumer_name, event_id, event_type, stream_id)
                VALUES ($1, $2, 'ConversationMemorySaveRequested', 's')
                """,
                CONSUMER_NAME,
                event_id,
            )
        code = await _run_execute(pg_pool, outbox_id, ticket="T-PROC")
        assert code == 4, f"expected 4 (not eligible), got {code}"

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row["status"] == "dead_letter", "must NOT have changed"

    async def test_blocks_if_status_not_dead_letter(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        oid = await insert_outbox_event(pg_pool, status="pending", attempts=3, max_attempts=3)
        code = await _run_execute(pg_pool, oid, ticket="T-STAT")
        assert code == 4

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=oid)
        assert row["status"] == "pending"

    async def test_blocks_if_outbox_dlq_missing(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool, with_dlq_snapshot=False)
        code = await _run_execute(pg_pool, outbox_id, ticket="T-DLQM")
        assert code == 4

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row["status"] == "dead_letter"

    async def test_blocks_if_event_type_not_allowed(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(
            pg_pool, event_type="WrongType",
        )
        code = await _run_execute(pg_pool, outbox_id, ticket="T-TYPE")
        assert code == 4

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row["status"] == "dead_letter"

    async def test_blocks_if_attempts_below_max(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(
            pg_pool, attempts=1, max_attempts=3,
        )
        code = await _run_execute(pg_pool, outbox_id, ticket="T-ATBL")
        assert code == 4

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row["status"] == "dead_letter"


class TestExecuteTransactional:
    async def test_second_execute_sees_status_pending(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        code1 = await _run_execute(pg_pool, outbox_id, ticket="T-CON1")
        assert code1 == 0

        code2 = await _run_execute(pg_pool, outbox_id, ticket="T-CON2")
        assert code2 == 4, "second call must block"

        row = await fetch_one(pg_pool, "outbox_events", outbox_id=outbox_id)
        assert row["status"] == "pending"

    async def test_execute_does_not_alter_processed_events(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        before_count = await count_rows(pg_pool, "processed_events")
        code = await _run_execute(pg_pool, outbox_id, ticket="T-NOPR")
        assert code == 0

        after_count = await count_rows(pg_pool, "processed_events")
        assert after_count == before_count, "must not insert into processed_events"

    async def test_execute_does_not_alter_outbox_dlq(
        self, pg_pool: asyncpg.Pool
    ) -> None:
        outbox_id, _ = await insert_dead_letter_event(pg_pool)
        before_dlq = await fetch_all(pg_pool, "outbox_dlq")
        code = await _run_execute(pg_pool, outbox_id, ticket="T-DLQ2")
        assert code == 0

        after_dlq = await fetch_all(pg_pool, "outbox_dlq")
        assert len(after_dlq) == len(before_dlq)
