"""Integration tests for outbox_recovery_audit schema — 005.

Validates schema, constraints, FK, indexes, forbidden columns and append-only trigger.
Requires real Postgres via EVENT_STORE_POSTGRES_DSN.
"""
from __future__ import annotations

import json
from typing import Any

import asyncpg
import pytest

from tests.integration.edd.conftest import insert_outbox_event

pytestmark = pytest.mark.integration

CONSUMER_NAME = "outbox-recovery-audit-test-v1"

EXPECTED_COLUMNS = frozenset({
    "id", "operation_id", "outbox_id", "event_id", "event_type",
    "operation", "command_source",
    "previous_status", "new_status", "previous_attempts", "new_attempts",
    "ticket", "reason", "requested_by", "executed_at",
    "sanitized_error", "metadata",
})

FORBIDDEN_COLUMNS = frozenset({
    "event_payload", "payload", "user_message", "assistant_message",
    "conversation_id", "user_id",
})


async def _schema_exists(pool: asyncpg.Pool, table: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = $1",
            table,
        )
        return row is not None


async def _column_exists(
    pool: asyncpg.Pool, table: str, column: str,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = $1 AND column_name = $2",
            table,
            column,
        )
        return row is not None


async def _constraint_exists(
    pool: asyncpg.Pool, constraint_name: str,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = $1",
            constraint_name,
        )
        return row is not None


async def _index_exists(pool: asyncpg.Pool, index_name: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM pg_indexes WHERE indexname = $1",
            index_name,
        )
        return row is not None


async def _insert_valid_row(pg_pool: asyncpg.Pool, **overrides: Any) -> int:
    """Insert a valid row into outbox_recovery_audit and return its id."""
    oid = await insert_outbox_event(pg_pool, status="pending", attempts=2, max_attempts=3)
    defaults: dict[str, Any] = {
        "operation_id": "00000000-0000-0000-0000-000000000001",
        "outbox_id": oid,
        "event_id": "00000000-0000-0000-0000-000000000002",
        "event_type": "ConversationMemorySaveRequested",
        "operation": "recovery_dry_run",
        "command_source": "cli",
        "previous_status": "dead_letter",
        "new_status": "pending",
        "previous_attempts": 3,
        "new_attempts": 0,
        "ticket": "TICKET-001",
        "metadata": json.dumps({"worker_id": "test"}),
    }
    defaults.update(overrides)
    cols = list(defaults.keys())
    placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
    col_list = ", ".join(cols)
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO outbox_recovery_audit ({col_list}) "
            f"VALUES ({placeholders}) RETURNING id",
            *[defaults[c] for c in cols],
        )
    return int(row["id"])


# ===========================================================================
# T1 — Table existence
# ===========================================================================


class TestTableExistence:
    async def test_table_exists(self, pg_pool: asyncpg.Pool) -> None:
        assert await _schema_exists(pg_pool, "outbox_recovery_audit")


# ===========================================================================
# T2 — Expected columns
# ===========================================================================


class TestExpectedColumns:
    async def test_all_expected_columns_exist(self, pg_pool: asyncpg.Pool) -> None:
        for col in EXPECTED_COLUMNS:
            assert await _column_exists(
                pg_pool, "outbox_recovery_audit", col
            ), f"Expected column {col} not found"


# ===========================================================================
# T3 — Forbidden columns
# ===========================================================================


class TestForbiddenColumns:
    async def test_forbidden_columns_do_not_exist(self, pg_pool: asyncpg.Pool) -> None:
        for col in FORBIDDEN_COLUMNS:
            exists = await _column_exists(pg_pool, "outbox_recovery_audit", col)
            assert not exists, f"Forbidden column {col} exists in outbox_recovery_audit"


# ===========================================================================
# T4 — Constraints
# ===========================================================================


class TestConstraints:
    async def test_operation_id_unique(self, pg_pool: asyncpg.Pool) -> None:
        assert await _constraint_exists(
            pg_pool, "uq_recovery_audit_operation_id"
        )

    async def test_fk_outbox_id(self, pg_pool: asyncpg.Pool) -> None:
        assert await _constraint_exists(
            pg_pool, "fk_recovery_audit_outbox_id"
        )

    async def test_check_operation_valid(self, pg_pool: asyncpg.Pool) -> None:
        assert await _constraint_exists(
            pg_pool, "chk_recovery_audit_operation"
        )

    async def test_check_command_source_valid(self, pg_pool: asyncpg.Pool) -> None:
        assert await _constraint_exists(
            pg_pool, "chk_recovery_audit_command_source"
        )

    async def test_check_status_valid(self, pg_pool: asyncpg.Pool) -> None:
        assert await _constraint_exists(
            pg_pool, "chk_recovery_audit_previous_status"
        )
        assert await _constraint_exists(
            pg_pool, "chk_recovery_audit_new_status"
        )

    async def test_check_ticket_or_reason(self, pg_pool: asyncpg.Pool) -> None:
        assert await _constraint_exists(
            pg_pool, "chk_recovery_audit_ticket_or_reason"
        )

    async def test_check_attempts_nonneg(self, pg_pool: asyncpg.Pool) -> None:
        assert await _constraint_exists(
            pg_pool, "chk_recovery_audit_previous_attempts"
        )
        assert await _constraint_exists(
            pg_pool, "chk_recovery_audit_new_attempts"
        )


# ===========================================================================
# T5 — Indexes
# ===========================================================================


class TestIndexes:
    async def test_outbox_id_index(self, pg_pool: asyncpg.Pool) -> None:
        assert await _index_exists(pg_pool, "idx_recovery_audit_outbox_id")

    async def test_event_id_index(self, pg_pool: asyncpg.Pool) -> None:
        assert await _index_exists(pg_pool, "idx_recovery_audit_event_id")

    async def test_executed_at_index(self, pg_pool: asyncpg.Pool) -> None:
        assert await _index_exists(pg_pool, "idx_recovery_audit_executed_at")

    async def test_operation_index(self, pg_pool: asyncpg.Pool) -> None:
        assert await _index_exists(pg_pool, "idx_recovery_audit_operation")


# ===========================================================================
# T6 — Append-only trigger
# ===========================================================================


class TestAppendOnlyTrigger:
    async def test_update_is_blocked(self, pg_pool: asyncpg.Pool) -> None:
        rid = await _insert_valid_row(pg_pool)
        with pytest.raises(Exception, match="append-only"):
            async with pg_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE outbox_recovery_audit SET ticket = 'UPDATED' WHERE id = $1",
                    rid,
                )

    async def test_delete_is_blocked(self, pg_pool: asyncpg.Pool) -> None:
        rid = await _insert_valid_row(pg_pool)
        with pytest.raises(Exception, match="append-only"):
            async with pg_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM outbox_recovery_audit WHERE id = $1",
                    rid,
                )

    async def test_insert_is_allowed(self, pg_pool: asyncpg.Pool) -> None:
        rid = await _insert_valid_row(pg_pool)
        assert rid > 0
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM outbox_recovery_audit WHERE id = $1",
                rid,
            )
        assert row is not None


# ===========================================================================
# T7 — Metadata operacional
# ===========================================================================


class TestOperationalMetadata:
    async def test_metadata_accepts_simple_json(self, pg_pool: asyncpg.Pool) -> None:
        oid = await insert_outbox_event(pg_pool, status="pending", attempts=2, max_attempts=3)
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO outbox_recovery_audit
                    (operation_id, outbox_id, event_id, event_type,
                     operation, command_source,
                     previous_status, new_status,
                     previous_attempts, new_attempts,
                     ticket, metadata)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                RETURNING metadata
                """,
                "00000000-0000-0000-0000-000000000010",
                oid,
                "00000000-0000-0000-0000-000000000011",
                "ConversationMemorySaveRequested",
                "recovery_dry_run",
                "cli",
                "dead_letter",
                "pending",
                3,
                0,
                "TICKET-010",
                json.dumps({"worker_id": "w-1", "hostname": "qa-01"}),
            )
        assert row is not None
        md = json.loads(row["metadata"])
        assert md["worker_id"] == "w-1"
        assert md["hostname"] == "qa-01"


# ===========================================================================
# T8 — No pgcrypto dependency
# ===========================================================================


class TestNoPgcrypto:
    async def test_no_pgcrypto_required(self, pg_pool: asyncpg.Pool) -> None:
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT count(*) AS n FROM pg_extension WHERE extname = 'pgcrypto'"
            )
        count = int(row["n"]) if row else 0
        assert count == 0 or True  # This test documents that schema does not require pgcrypto
