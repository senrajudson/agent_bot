"""Conftest for EDD integration tests against real Postgres.

Provides:
- Skip when EVENT_STORE_POSTGRES_DSN is not set.
- DSN validation (must start with postgresql:// or postgres://).
- Schema-name validation regex.
- Allowed-tables whitelist for SQL helpers.

This module is intentionally read-only at import time: it does not open
any Postgres connection, does not read .env, and does not execute any SQL.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import asyncpg
import pytest

from app.domain.events import (
    AgentRouteSelected,
    ConversationMemoryLoaded,
    DomainEvent,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DSN_ENV_VAR = "EVENT_STORE_POSTGRES_DSN"
SCHEMA_PREFIX = "edd_test_"
SCHEMA_RE = r"^edd_test_[a-f0-9]{32}$"

SQL_FILES = (
    "app/infrastructure/event_store/sql/001_create_event_store_events.sql",
    "db/edd/002_create_outbox_events.sql",
    "db/edd/003_create_processed_events.sql",
    "db/edd/004_create_outbox_dlq.sql",
    "db/edd/005_create_outbox_recovery_audit.sql",
)

ALLOWED_TABLES = frozenset({
    "event_store_events",
    "outbox_events",
    "processed_events",
    "outbox_dlq",
    "outbox_recovery_audit",
})

ALLOWED_OUTBOX_WHERE_COLS = frozenset({
    "outbox_id",
    "event_id",
    "stream_id",
    "stream_version",
    "status",
    "attempts",
})

ALLOWED_PROCESSED_WHERE_COLS = frozenset({
    "consumer_name",
    "event_id",
    "outbox_id",
})

ALLOWED_EVENT_STORE_WHERE_COLS = frozenset({
    "event_id",
    "stream_id",
    "stream_version",
})

ALLOWED_DLQ_WHERE_COLS = frozenset({
    "outbox_id",
    "event_id",
    "stream_id",
})

ALLOWED_RECOVERY_AUDIT_WHERE_COLS = frozenset({
    "outbox_id",
    "event_id",
    "operation_id",
    "operation",
    "command_source",
})

TABLE_WHERE_COLS: dict[str, frozenset[str]] = {
    "outbox_events": ALLOWED_OUTBOX_WHERE_COLS,
    "processed_events": ALLOWED_PROCESSED_WHERE_COLS,
    "event_store_events": ALLOWED_EVENT_STORE_WHERE_COLS,
    "outbox_dlq": ALLOWED_DLQ_WHERE_COLS,
    "outbox_recovery_audit": ALLOWED_RECOVERY_AUDIT_WHERE_COLS,
}


# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------

# conftest.py is at tests/integration/edd/conftest.py → parents[3] = repo root
REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Gate marker (all tests in this dir are integration by default)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _validate_schema_name(name: str) -> None:
    if not re.fullmatch(SCHEMA_RE, name):
        raise ValueError(
            f"schema name {name!r} does not match {SCHEMA_RE!r}"
        )


# ---------------------------------------------------------------------------
# DSN fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def event_store_dsn() -> str:
    dsn = os.environ.get(DSN_ENV_VAR)
    if not dsn:
        pytest.skip(
            f"{DSN_ENV_VAR} is not set; EDD integration tests skipped. "
            f"Set {DSN_ENV_VAR} to a real Postgres DSN to run."
        )
    if not (dsn.startswith("postgresql://") or dsn.startswith("postgres://")):
        raise ValueError(
            f"{DSN_ENV_VAR} must start with postgresql:// or postgres://"
        )
    return dsn


# ---------------------------------------------------------------------------
# Schema descartável
# ---------------------------------------------------------------------------


@pytest.fixture
def schema_name() -> str:
    name = f"{SCHEMA_PREFIX}{uuid.uuid4().hex}"
    _validate_schema_name(name)
    return name


@pytest.fixture
async def admin_connection(
    event_store_dsn: str,
) -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(event_store_dsn)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def created_schema(
    admin_connection: asyncpg.Connection,
    schema_name: str,
) -> AsyncIterator[str]:
    await admin_connection.execute(f'CREATE SCHEMA "{schema_name}"')
    try:
        yield schema_name
    finally:
        await admin_connection.execute(
            f'DROP SCHEMA "{schema_name}" CASCADE'
        )


@pytest.fixture
async def applied_sqls(
    created_schema: str,
    admin_connection: asyncpg.Connection,
) -> AsyncIterator[str]:
    await admin_connection.execute(
        f'SET search_path TO "{created_schema}"'
    )
    try:
        for rel in SQL_FILES:
            sql_path = REPO_ROOT / rel
            sql_text = sql_path.read_text(encoding="utf-8")
            await admin_connection.execute(sql_text)
        yield created_schema
    finally:
        await admin_connection.execute("RESET search_path")


@pytest.fixture
async def pg_pool(
    applied_sqls: str,
    event_store_dsn: str,
) -> AsyncIterator[asyncpg.Pool]:
    pool = await asyncpg.create_pool(
        event_store_dsn,
        min_size=1,
        max_size=4,
        server_settings={"search_path": applied_sqls},
    )
    try:
        yield pool
    finally:
        await pool.close()


# ---------------------------------------------------------------------------
# Event factories
# ---------------------------------------------------------------------------


def make_test_event(**kwargs: Any) -> DomainEvent:
    """Build a DomainEvent with sensible defaults. Pass overrides via kwargs."""
    return DomainEvent(**kwargs)


def make_agent_event(**kwargs: Any) -> AgentRouteSelected:
    """Build an AgentRouteSelected. Defaults: route='pims', message_id='m1'."""
    defaults: dict[str, Any] = {"route": "pims", "message_id": "m1"}
    defaults.update(kwargs)
    return AgentRouteSelected(**defaults)


def make_memory_loaded(**kwargs: Any) -> ConversationMemoryLoaded:
    """Build a ConversationMemoryLoaded. Defaults: turns_count=0, max_turns=0."""
    defaults: dict[str, Any] = {"turns_count": 0, "max_turns": 0}
    defaults.update(kwargs)
    return ConversationMemoryLoaded(**defaults)


# ---------------------------------------------------------------------------
# Outbox / table helpers
# ---------------------------------------------------------------------------


def _validate_table(table: str) -> frozenset[str]:
    if table not in ALLOWED_TABLES:
        raise ValueError(
            f"table {table!r} not in ALLOWED_TABLES {sorted(ALLOWED_TABLES)}"
        )
    return TABLE_WHERE_COLS[table]


def _validate_where(table: str, where: dict[str, Any]) -> list[str]:
    allowed_cols = _validate_table(table)
    for col in where:
        if col not in allowed_cols:
            raise ValueError(
                f"column {col!r} not allowed for table {table!r}; "
                f"allowed: {sorted(allowed_cols)}"
            )
    return list(where.keys())


async def insert_outbox_event(pool: asyncpg.Pool, **kwargs: Any) -> int:
    """Insert a row in outbox_events with sensible defaults. Returns outbox_id."""
    now = datetime.now(timezone.utc)
    defaults: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "stream_id": "test-stream",
        "stream_version": 1,
        "aggregate_id": None,
        "event_type": "InboundMessageReceived",
        "event_payload": json.dumps({"message_id": "m1"}),
        "status": "pending",
        "attempts": 0,
        "max_attempts": 3,
        "available_at": now,
        "correlation_id": None,
        "causation_id": None,
        "metadata": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kwargs)
    cols = list(defaults.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    col_list = ", ".join(cols)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO outbox_events ({col_list}) VALUES ({placeholders}) "
            f"RETURNING outbox_id",
            *[defaults[c] for c in cols],
        )
    return int(row["outbox_id"])


async def fetch_one(
    pool: asyncpg.Pool, table: str, **where: Any
) -> dict[str, Any] | None:
    """SELECT first row matching where clauses. Whitelisted table/columns."""
    _validate_where(table, where)
    where_clauses = " AND ".join(f"{c} = ${i + 1}" for i, c in enumerate(where.keys()))
    sql = f"SELECT * FROM {table}"
    if where_clauses:
        sql += f" WHERE {where_clauses} LIMIT 1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, *where.values())
    return dict(row) if row is not None else None


async def fetch_all(
    pool: asyncpg.Pool, table: str, order_by: str | None = None
) -> list[dict[str, Any]]:
    """SELECT all rows from table. Whitelisted table; optional whitelisted order_by."""
    _validate_table(table)
    if order_by is not None:
        allowed_cols = TABLE_WHERE_COLS[table]
        if order_by not in allowed_cols:
            raise ValueError(
                f"order_by column {order_by!r} not allowed for table {table!r}"
            )
    sql = f"SELECT * FROM {table}"
    if order_by:
        sql += f" ORDER BY {order_by} ASC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


async def count_rows(
    pool: asyncpg.Pool, table: str, **where: Any
) -> int:
    """Count rows matching where. Whitelisted table/columns."""
    _validate_where(table, where)
    where_clauses = " AND ".join(f"{c} = ${i + 1}" for i, c in enumerate(where.keys()))
    sql = f"SELECT count(*) AS n FROM {table}"
    if where_clauses:
        sql += f" WHERE {where_clauses}"
    async with pool.acquire() as conn:
        n = await conn.fetchval(sql, *where.values())
    return int(n)


async def assert_outbox_status(
    pool: asyncpg.Pool, outbox_id: int, expected_status: str
) -> None:
    row = await fetch_one(pool, "outbox_events", outbox_id=outbox_id)
    assert row is not None, f"outbox_id={outbox_id} not found"
    actual = row["status"]
    assert actual == expected_status, (
        f"outbox_id={outbox_id} expected status={expected_status!r} "
        f"but got {actual!r}"
    )
