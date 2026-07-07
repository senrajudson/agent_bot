"""Unit tests for scripts/inspect_outbox.py — 100% fakes, no Postgres."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Ensure scripts/ is importable
_SCRIPTS = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import inspect_outbox  # noqa: E402

# =========================================================================
# Fakes
# =========================================================================


class FakeAsyncPGConnection:
    """Fake asyncpg connection that records SQL and returns empty rows."""

    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.fetched_sql: list[str] = []
        self._fetch_result: list[Any] = []
        self._execute_side_effect: Exception | None = None

    def set_fetch_result(self, rows: list[dict[str, Any]]) -> None:
        self._fetch_result = rows

    def set_execute_side_effect(self, exc: Exception) -> None:
        self._execute_side_effect = exc

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed_sql.append(sql)
        if self._execute_side_effect:
            raise self._execute_side_effect
        return ""

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        self.fetched_sql.append(sql)
        return self._fetch_result


class FakeAsyncPGPool:
    """Fake asyncpg pool returning a FakeAsyncPGConnection."""

    def __init__(self) -> None:
        self.conn = FakeAsyncPGConnection()

    def set_fetch_result(self, rows: list[dict[str, Any]]) -> None:
        self.conn.set_fetch_result(rows)

    def set_execute_side_effect(self, exc: Exception) -> None:
        self.conn.set_execute_side_effect(exc)

    def acquire(self) -> Any:
        class _Ctx:
            def __init__(self, conn: FakeAsyncPGConnection) -> None:
                self._conn = conn

            async def __aenter__(self) -> FakeAsyncPGConnection:
                return self._conn

            async def __aexit__(self, *args: Any) -> None:
                pass

        return _Ctx(self.conn)

    async def __aenter__(self) -> "FakeAsyncPGPool":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(autouse=True)
def _clear_env() -> None:
    """Ensure EVENT_STORE_POSTGRES_DSN is not set by default in tests."""
    saved = os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)
    yield
    if saved is not None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = saved


@pytest.fixture
def fake_pool() -> FakeAsyncPGPool:
    return FakeAsyncPGPool()


# =========================================================================
# Helpers para testes T6
# =========================================================================

_QUERY_MAP = {
    "outbox-pending": inspect_outbox._query_pending,
    "outbox-locked": inspect_outbox._query_locked,
    "outbox-dlq": inspect_outbox._query_dlq,
}


def _run_query(sub: str, fake_pool: FakeAsyncPGPool, **extra: Any) -> None:
    flags = [sub]
    for k, v in extra.items():
        k = k.replace("_", "-")
        flags.append(f"--{k}")
        flags.append(str(v))
    args = inspect_outbox._parse_args(flags)
    asyncio.run(_QUERY_MAP[sub](fake_pool, args))


# =========================================================================
# T5 — Parser, guards, exit codes
# =========================================================================


class TestT5ParserGuards:
    def test_main_help_exits_0(self) -> None:
        with pytest.raises(SystemExit) as exc:
            inspect_outbox.main(["--help"])
        assert exc.value.code == 0

    def test_subcommand_help_exits_0(self) -> None:
        for cmd in ("outbox-pending", "outbox-locked", "outbox-dlq"):
            with pytest.raises(SystemExit) as exc:
                inspect_outbox.main([cmd, "--help"])
            assert exc.value.code == 0, f"{cmd} --help"

    def test_no_subcommand_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            inspect_outbox.main([])
        assert exc.value.code == 1

    def test_invalid_subcommand_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            inspect_outbox.main(["invalid"])
        assert exc.value.code == 1

    def test_destructive_command_not_accepted(self) -> None:
        with pytest.raises(SystemExit):
            inspect_outbox._parse_args(["outbox-pending", "--purge"])

    def test_dsn_missing_exits_2(self) -> None:
        assert inspect_outbox.main(["outbox-pending"]) == 2

    def test_dsn_remote_exits_2(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://u:pass@db.example.com:5432/events"
        )
        assert inspect_outbox.main(["outbox-pending"]) == 2

    def test_dsn_local_accepted(self, fake_pool: FakeAsyncPGPool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://u:pass@127.0.0.1:5432/events"
        )
        with patch("asyncpg.create_pool", return_value=fake_pool):
            code = inspect_outbox.main(["outbox-pending"])
        assert code != 2, "DSN local foi rejeitado"

    def test_dsn_not_printed_in_output(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://secret:token@127.0.0.1:5432/events"
        )
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code, dsn = inspect_outbox._check_dsn()
        combined = stdout.getvalue() + stderr.getvalue()
        assert "secret" not in combined, "DSN secret vazou em output"
        assert "token" not in combined, "DSN token vazou em output"
        assert code == 0
        assert dsn == "postgresql://secret:token@127.0.0.1:5432/events"

    def test_outbox_dispatcher_enabled_not_required(self) -> None:
        """The script does NOT check OUTBOX_DISPATCHER_ENABLED."""
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://u:p@127.0.0.1:5432/events"
        )
        os.environ.pop("OUTBOX_DISPATCHER_ENABLED", None)
        with patch("asyncpg.create_pool", side_effect=Exception("pool fail")):
            code = inspect_outbox.main(["outbox-pending"])
        assert code == 4, "DSN foi rejeitado mesmo sem OUTBOX_DISPATCHER_ENABLED"

    def test_limit_default(self) -> None:
        args = inspect_outbox._parse_args(["outbox-pending"])
        assert args.limit == 50

    def test_limit_500_accepted(self) -> None:
        args = inspect_outbox._parse_args(["outbox-pending", "--limit", "500"])
        assert args.limit == 500

    def test_limit_0_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            inspect_outbox._parse_args(["outbox-pending", "--limit", "0"])
        assert exc.value.code == 1

    def test_limit_501_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            inspect_outbox._parse_args(["outbox-pending", "--limit", "501"])
        assert exc.value.code == 1

    def test_limit_abc_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            inspect_outbox._parse_args(["outbox-pending", "--limit", "abc"])
        assert exc.value.code == 1


# =========================================================================
# T6 — Query builders and filters
# =========================================================================


class TestT6Queries:
    @pytest.mark.parametrize("sub", ["outbox-pending", "outbox-locked", "outbox-dlq"])
    def test_query_is_select(self, sub: str, fake_pool: FakeAsyncPGPool) -> None:
        _run_query(sub, fake_pool)
        sql = fake_pool.conn.fetched_sql[0]
        assert sql.strip().upper().startswith("SELECT"), f"{sub} não é SELECT"

    @pytest.mark.parametrize("sub", ["outbox-pending", "outbox-locked", "outbox-dlq"])
    def test_query_no_destructive_ops(self, sub: str, fake_pool: FakeAsyncPGPool) -> None:
        _run_query(sub, fake_pool)
        sql = fake_pool.conn.fetched_sql[0].upper()
        for op in ("DELETE", "INSERT", "TRUNCATE", "DROP", "ALTER"):
            assert op not in sql, f"{sub} contém {op}"
        # UPDATE é uma palavra reservada, mas aparece em UPDATED_AT;
        # verificamos com borda de palavra
        import re
        assert not re.search(r'\bUPDATE\b', sql), f"{sub} contém UPDATE"

    @pytest.mark.parametrize("sub", ["outbox-pending", "outbox-locked", "outbox-dlq"])
    def test_query_no_sensitive_columns(self, sub: str, fake_pool: FakeAsyncPGPool) -> None:
        _run_query(sub, fake_pool)
        sql = fake_pool.conn.fetched_sql[0].upper()
        for col in ("EVENT_PAYLOAD", "USER_MESSAGE", "ASSISTANT_MESSAGE"):
            assert col not in sql, f"{sub} referencia {col}"

    def test_event_type_filter(self, fake_pool: FakeAsyncPGPool) -> None:
        _run_query("outbox-pending", fake_pool, event_type="ConversationMemorySaveRequested")
        sql = fake_pool.conn.fetched_sql[0]
        assert "$1" in sql or "%s" in sql  # parametrizado

    def test_since_filter_pending(self, fake_pool: FakeAsyncPGPool) -> None:
        _run_query("outbox-pending", fake_pool, since="2026-07-01")
        sql = fake_pool.conn.fetched_sql[0]
        assert "available_at" in sql.lower()

    def test_since_filter_dlq(self, fake_pool: FakeAsyncPGPool) -> None:
        _run_query("outbox-dlq", fake_pool, since="2026-07-01")
        sql = fake_pool.conn.fetched_sql[0]
        assert "moved_to_dlq_at" in sql.lower()

    def test_outbox_id_filter(self, fake_pool: FakeAsyncPGPool) -> None:
        _run_query("outbox-pending", fake_pool, outbox_id=42)
        assert fake_pool.conn.fetched_sql[0] is not None

    def test_conversation_id_uses_aggregate_id(self, fake_pool: FakeAsyncPGPool) -> None:
        _run_query("outbox-pending", fake_pool, conversation_id="conv-123")
        sql = fake_pool.conn.fetched_sql[0].lower()
        assert "aggregate_id" in sql
        assert "event_payload" not in sql

    def test_with_error_adds_filter(self, fake_pool: FakeAsyncPGPool) -> None:
        args = inspect_outbox._parse_args(["outbox-pending", "--with-error"])
        assert args.with_error is True


# =========================================================================
# T7 — Output formatting and sanitization
# =========================================================================


class TestT7Output:
    SENSITIVE_KEYS = ("event_payload", "metadata", "user_message", "assistant_message")

    def _sample_records(self) -> list[dict[str, Any]]:
        return [
            {
                "outbox_id": 1,
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": "ConversationMemorySaveRequested",
                "attempts": 3,
                "max_attempts": 3,
                "has_error": True,
                "last_error_class": "RuntimeError",
                "last_error": "terminal failure: user_message=USER_SECRET",
                "final_error_class": "RuntimeError",
                "final_error": "terminal failure: user_message=USER_SECRET",
                "stream_id": "conversation:conv-1",
                "aggregate_id": "conv-1",
            }
        ]

    def test_default_output_no_sensitive_data(self) -> None:
        safe = inspect_outbox._sanitize_records(
            self._sample_records(),
            inspect_outbox._parse_args(["outbox-dlq"]),
        )
        for row in safe:
            for key in self.SENSITIVE_KEYS:
                assert key not in row, f"{key} apareceu na saída padrão"

    def test_default_output_no_conversation_id_column(self) -> None:
        safe = inspect_outbox._sanitize_records(
            self._sample_records(),
            inspect_outbox._parse_args(["outbox-dlq"]),
        )
        for row in safe:
            assert "conversation_id" not in row, "conversation_id apareceu na saída"

    def test_default_output_no_dsn_raw(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            inspect_outbox._format_and_print(
                self._sample_records(),
                inspect_outbox._parse_args(["outbox-dlq"]),
                "postgresql://secret:token@127.0.0.1:5432/events",
            )
        output = stdout.getvalue()
        assert "[REDACTED]" in output
        assert "secret" not in output

    def test_show_sanitized_error_redacts_sentinel(self) -> None:
        args = inspect_outbox._parse_args(["outbox-pending", "--show-sanitized-error"])
        safe = inspect_outbox._sanitize_records(self._sample_records(), args)
        for row in safe:
            err = row.get("last_error") or row.get("final_error") or ""
            assert "<REDACTED>" in err, "erro não foi sanitizado"

    def test_show_sanitized_error_no_payload(self) -> None:
        args = inspect_outbox._parse_args(["outbox-pending", "--show-sanitized-error"])
        safe = inspect_outbox._sanitize_records(self._sample_records(), args)
        for row in safe:
            for key in self.SENSITIVE_KEYS:
                assert key not in row, f"{key} apareceu com --show-sanitized-error"

    def test_show_sanitized_error_truncates(self) -> None:
        records = [{"last_error": "x" * 500}]
        args = inspect_outbox._parse_args(["outbox-pending", "--show-sanitized-error"])
        safe = inspect_outbox._sanitize_records(records, args)
        err = safe[0].get("last_error", "")
        assert len(err) <= 200, f"erro não truncado: {len(err)} chars"

    def test_json_output_valid(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            inspect_outbox._format_and_print(
                self._sample_records(),
                inspect_outbox._parse_args(["outbox-dlq", "--json"]),
                "postgresql://u:p@127.0.0.1:5432/db",
            )
        data = json.loads(stdout.getvalue())
        assert "timestamp_utc" in data
        assert data["command"] == "outbox-dlq"
        assert "filters" in data
        assert data["count"] == 1
        assert "items" in data
        assert len(data["items"]) == 1

    def test_json_not_contains_sensitive(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            inspect_outbox._format_and_print(
                self._sample_records(),
                inspect_outbox._parse_args(["outbox-dlq", "--json"]),
                "postgresql://u:p@127.0.0.1:5432/db",
            )
        text = stdout.getvalue()
        for key in self.SENSITIVE_KEYS:
            assert key not in text, f"{key} no JSON"

    def test_stdout_vs_stderr(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            inspect_outbox._format_and_print(
                self._sample_records(),
                inspect_outbox._parse_args(["outbox-dlq"]),
                "postgresql://u:p@127.0.0.1:5432/db",
            )
        assert stdout.getvalue(), "stdout vazio"
        assert "[REDACTED]" in stdout.getvalue()

    def test_header_contains_timestamp_dsn_filters_count(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            inspect_outbox._format_and_print(
                self._sample_records(),
                inspect_outbox._parse_args(["outbox-dlq"]),
                "postgresql://u:p@127.0.0.1:5432/db",
            )
        output = stdout.getvalue()
        assert "dsn:" in output
        assert "[REDACTED]" in output
        assert "command:" in output
        assert "count:" in output
        assert "outbox-dlq" in output


# =========================================================================
# T8 — Schema missing and query error
# =========================================================================


class TestT8SchemaQueryErrors:
    @pytest.mark.parametrize("sub", ["outbox-pending", "outbox-locked", "outbox-dlq"])
    def test_schema_missing_exits_3(self, sub: str, fake_pool: FakeAsyncPGPool) -> None:
        fake_pool.conn.set_execute_side_effect(
            __import__("asyncpg").UndefinedTableError("relation does not exist")
        )
        code = asyncio.run(inspect_outbox._verify_schema(fake_pool, ["outbox_events"]))
        assert code == 3, f"{sub}: schema ausente não retornou 3"

    def test_schema_missing_message_mentions_apply_script(
        self, caplog: pytest.LogCaptureFixture, fake_pool: FakeAsyncPGPool
    ) -> None:
        fake_pool.conn.set_execute_side_effect(
            __import__("asyncpg").UndefinedTableError("relation does not exist")
        )
        asyncio.run(inspect_outbox._verify_schema(fake_pool, ["outbox_events"]))
        assert any(
            "apply_edd_schema" in rec.message for rec in caplog.records
        ), "schema ausente deve mencionar apply_edd_schema.sh"

    def test_outbox_dlq_validates_extra_table(
        self, caplog: pytest.LogCaptureFixture, fake_pool: FakeAsyncPGPool
    ) -> None:
        fake_pool.conn.set_execute_side_effect(
            __import__("asyncpg").UndefinedTableError("relation does not exist")
        )
        code = asyncio.run(
            inspect_outbox._verify_schema(fake_pool, ["outbox_events", "outbox_dlq"])
        )
        assert code == 3
        assert any(
            "outbox_events" in rec.message or "outbox_dlq" in rec.message
            for rec in caplog.records
        ), "mensagem deve mencionar tabela ausente"

    def test_query_error_exits_4(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://u:p@127.0.0.1:5432/events"
        )
        with patch("asyncpg.create_pool", side_effect=Exception("connection refused")):
            code = inspect_outbox.main(["outbox-pending"])
        assert code == 4, "erro de conexão não retornou 4"

    def test_query_error_does_not_leak_dsn(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://secret:token@127.0.0.1:5432/events"
        )
        stderr = StringIO()
        with redirect_stderr(stderr), patch(
            "asyncpg.create_pool", side_effect=Exception("connection refused")
        ):
            inspect_outbox.main(["outbox-pending"])
        assert "postgresql://" not in stderr.getvalue()
        assert "secret" not in stderr.getvalue()

    def test_unexpected_exception_does_not_leak_payload(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://u:p@127.0.0.1:5432/events"
        )
        with patch(
            "asyncpg.create_pool",
            side_effect=RuntimeError(
                "unexpected failure with user_message=SENSITIVE"
            ),
        ):
            inspect_outbox.main(["outbox-pending"])
        assert any(
            "unexpected failure" in rec.message
            for rec in caplog.records
        ), "erro deve estar no log"
        assert not any(
            "SENSITIVE" in rec.message
            for rec in caplog.records
        ), "SENSITIVE não deve vazar em log"


# =========================================================================
# _redact_dsn helper
# =========================================================================


class TestRedactDsn:
    def test_redact_dsn_hides_credentials(self) -> None:
        dsn = "postgresql://user:password@127.0.0.1:5432/events"
        redacted = inspect_outbox._redact_dsn(dsn)
        assert "user:" not in redacted
        assert "password" not in redacted
        assert "[REDACTED]" in redacted
