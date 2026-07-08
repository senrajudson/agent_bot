"""Unit tests for scripts/recover_outbox_event.py — 100% fakes, no Postgres."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import deque
from io import StringIO
from pathlib import Path
from typing import Any, Deque
from unittest.mock import AsyncMock, patch

import pytest

_SCRIPTS = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import recover_outbox_event  # noqa: E402


# =========================================================================
# Fakes
# =========================================================================


class FakeAsyncPGConnection:
    """Fake asyncpg connection with configurable fetchrow per call."""

    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.fetched_sql: list[str] = []
        self._fetchrow_results: Deque[dict[str, Any] | None] = deque()
        self._fetch_result: list[dict[str, Any]] = []
        self._execute_side_effect: Exception | None = None

    def set_fetchrow_results(
        self, results: list[dict[str, Any] | None]
    ) -> None:
        self._fetchrow_results = deque(results)

    def set_fetch_result(self, rows: list[dict[str, Any]]) -> None:
        self._fetch_result = rows

    def set_execute_side_effect(self, exc: Exception | None) -> None:
        self._execute_side_effect = exc

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed_sql.append(sql)
        if self._execute_side_effect:
            raise self._execute_side_effect
        return ""

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.fetched_sql.append(sql)
        return self._fetch_result

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        self.fetched_sql.append(sql)
        if self._fetchrow_results:
            return self._fetchrow_results.popleft()
        return None


class FakeAsyncPGPool:
    """Fake asyncpg pool returning a FakeAsyncPGConnection."""

    def __init__(self) -> None:
        self.conn = FakeAsyncPGConnection()

    def acquire(self) -> Any:
        class _Ctx:
            def __init__(self, conn: FakeAsyncPGConnection) -> None:
                self._conn = conn

            async def __aenter__(self) -> FakeAsyncPGConnection:
                return self._conn

            async def __aexit__(self, *args: Any) -> None:
                pass

        return _Ctx(self.conn)

    async def __aenter__(self) -> FakeAsyncPGPool:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(autouse=True)
def _clear_env() -> None:
    saved = os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)
    yield
    if saved is not None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = saved


@pytest.fixture
def fake_pool() -> FakeAsyncPGPool:
    return FakeAsyncPGPool()


# =========================================================================
# Helpers
# =========================================================================


_OUTBOX_EVENT_DEAD_LETTER = {
    "outbox_id": 1,
    "event_id": "evt-dlq-001",
    "event_type": "ConversationMemorySaveRequested",
    "status": "dead_letter",
    "attempts": 3,
    "max_attempts": 3,
}


_DSN_OK = "postgresql://u:p@127.0.0.1:5432/events"


# =========================================================================
# Parser and gates
# =========================================================================


class TestParserAndGates:
    def test_help_exits_0(self) -> None:
        with pytest.raises(SystemExit) as exc:
            recover_outbox_event._parse_args(["--help"])
        assert exc.value.code == 0

    def test_outbox_id_required(self) -> None:
        with pytest.raises(SystemExit) as exc:
            recover_outbox_event._parse_args(["--ticket", "T1"])
        assert exc.value.code == 1

    def test_ticket_or_reason_required(self) -> None:
        with pytest.raises(SystemExit) as exc:
            recover_outbox_event._parse_args(["--outbox-id", "1"])
        assert exc.value.code == 1

    def test_dsn_missing_exits_2(self) -> None:
        code, _ = recover_outbox_event._check_dsn()
        assert code == 2

    def test_dsn_remote_exits_2(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://u:pass@db.example.com:5432/events"
        )
        code, _ = recover_outbox_event._check_dsn()
        assert code == 2

    def test_dsn_local_accepted(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        code, dsn = recover_outbox_event._check_dsn()
        assert code == 0
        assert dsn == _DSN_OK

    def test_execute_without_confirmation_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            recover_outbox_event._parse_args(
                ["--outbox-id", "1", "--ticket", "T1", "--execute"]
            )
        assert exc.value.code == 1

    def test_execute_with_confirmation_passes_parser(self) -> None:
        args = recover_outbox_event._parse_args(
            ["--outbox-id", "1", "--ticket", "T1",
             "--execute", "--yes-i-confirm-recovery"]
        )
        assert args.execute is True
        assert args.yes_i_confirm_recovery is True


# =========================================================================
# Eligibility checks
# =========================================================================


class TestEligibility:
    @pytest.mark.asyncio
    async def test_outbox_not_found(self, fake_pool: FakeAsyncPGPool) -> None:
        fake_pool.conn.set_fetchrow_results([None])
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=999, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["eligible"] is False
        assert rd["reason_code"] == "outbox_not_found"

    @pytest.mark.asyncio
    async def test_status_not_dead_letter(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        row = dict(_OUTBOX_EVENT_DEAD_LETTER, status="pending")
        fake_pool.conn.set_fetchrow_results([row])
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=1, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["eligible"] is False
        assert rd["reason_code"] == "status_not_dead_letter"

    @pytest.mark.asyncio
    async def test_event_type_not_allowed(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        row = dict(_OUTBOX_EVENT_DEAD_LETTER, event_type="WrongType")
        fake_pool.conn.set_fetchrow_results([row])
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=1, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["eligible"] is False
        assert rd["reason_code"] == "event_type_not_allowed"

    @pytest.mark.asyncio
    async def test_attempts_below_max(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        row = dict(_OUTBOX_EVENT_DEAD_LETTER, attempts=1)
        fake_pool.conn.set_fetchrow_results([row])
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=1, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["eligible"] is False
        assert rd["reason_code"] == "attempts_below_max"

    @pytest.mark.asyncio
    async def test_dlq_snapshot_missing(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        fake_pool.conn.set_fetchrow_results(
            [_OUTBOX_EVENT_DEAD_LETTER, None],
        )
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=1, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["eligible"] is False
        assert rd["reason_code"] == "dlq_snapshot_missing"

    @pytest.mark.asyncio
    async def test_processed_events_already_marked(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        fake_pool.conn.set_fetchrow_results(
            [_OUTBOX_EVENT_DEAD_LETTER, {"dlq_id": 1}, {"processed_id": 1}],
        )
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=1, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["eligible"] is False
        assert rd["reason_code"] == "processed_events_already_marked"

    @pytest.mark.asyncio
    async def test_eligible_true(self, fake_pool: FakeAsyncPGPool) -> None:
        fake_pool.conn.set_fetchrow_results(
            [_OUTBOX_EVENT_DEAD_LETTER, {"dlq_id": 1}, None],
        )
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=1, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["eligible"] is True
        assert rd["reason_code"] is None
        assert rd["event_id"] == "evt-dlq-001"
        assert rd["event_type"] == "ConversationMemorySaveRequested"
        assert rd["status"] == "dead_letter"
        assert rd["attempts"] == 3
        assert rd["max_attempts"] == 3


# =========================================================================
# Read-only checks
# =========================================================================


class TestReadOnly:
    @pytest.mark.asyncio
    async def test_queries_are_select_only(self, fake_pool: FakeAsyncPGPool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK

        async def _fake_create_pool(*args: Any, **kwargs: Any) -> FakeAsyncPGPool:
            return fake_pool

        fake_pool.conn.set_fetchrow_results(
            [_OUTBOX_EVENT_DEAD_LETTER, {"dlq_id": 1}, None],
        )
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            code = await recover_outbox_event._run_once(_DSN_OK, _make_args(1))
        assert code == 0
        all_sql = " ".join(fake_pool.conn.fetched_sql)
        assert "SELECT" in all_sql
        assert "UPDATE" not in all_sql
        assert "DELETE" not in all_sql
        assert "INSERT" not in all_sql
        assert "TRUNCATE" not in all_sql

    def test_dispatcher_not_called(self) -> None:
        src = Path(recover_outbox_event.__file__).read_text()
        assert "OutboxDispatcher" not in src
        assert "dispatch_once" not in src


def _make_args(outbox_id: int) -> argparse.Namespace:
    """Build argparse.Namespace matching the real parser."""
    return recover_outbox_event._parse_args(
        ["--outbox-id", str(outbox_id), "--ticket", "T1"]
    )


# =========================================================================
# Schema validation
# =========================================================================


class TestSchema:
    @pytest.mark.asyncio
    async def test_schema_missing_returns_3(self, fake_pool: FakeAsyncPGPool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK

        async def _fake_create_pool(*args: Any, **kwargs: Any) -> FakeAsyncPGPool:
            return fake_pool

        fake_pool.conn.set_execute_side_effect(
            Exception("relation outbox_events does not exist")
        )
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            code = await recover_outbox_event._run_once(_DSN_OK, _make_args(1))
        assert code == 3


# =========================================================================
# Payload safety
# =========================================================================


class TestPayloadSafety:
    @pytest.mark.asyncio
    async def test_output_does_not_contain_payload(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        fake_pool.conn.set_fetchrow_results(
            [_OUTBOX_EVENT_DEAD_LETTER, {"dlq_id": 1}, None],
        )
        stdout, _ = await _run_capture_output(fake_pool, 1)
        assert "event_payload" not in stdout
        assert "user_message" not in stdout
        assert "assistant_message" not in stdout
        assert "secret_sentinel" not in stdout

    @pytest.mark.asyncio
    async def test_dsn_not_in_output(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        fake_pool.conn.set_fetchrow_results(
            [_OUTBOX_EVENT_DEAD_LETTER, {"dlq_id": 1}, None],
        )
        stdout, _ = await _run_capture_output(fake_pool, 1)
        assert "secret" not in stdout


async def _run_capture_output(
    pool: FakeAsyncPGPool, outbox_id: int
) -> tuple[str, str]:
    import argparse

    async def _fake_create_pool(*args: Any, **kwargs: Any) -> FakeAsyncPGPool:
        return pool

    stdout = StringIO()
    stderr = StringIO()
    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
        mock_pool.side_effect = _fake_create_pool
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            args = _make_args(outbox_id)
            code = await recover_outbox_event._run_once(_DSN_OK, args)
    assert code == 0, f"code={code}, stderr={stderr.getvalue()}"
    return stdout.getvalue(), stderr.getvalue()


# =========================================================================
# Output format
# =========================================================================


class TestOutputFormat:
    @pytest.mark.asyncio
    async def test_text_output_contains_eligible_true(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        fake_pool.conn.set_fetchrow_results(
            [_OUTBOX_EVENT_DEAD_LETTER, {"dlq_id": 1}, None],
        )
        stdout, _ = await _run_capture_output(fake_pool, 1)
        assert "eligible:" in stdout
        assert "sim" in stdout

    @pytest.mark.asyncio
    async def test_json_output_eligible_false(
        self, fake_pool: FakeAsyncPGPool
    ) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        fake_pool.conn.set_fetchrow_results([None])

        async def _fake_create_pool(*args: Any, **kwargs: Any) -> FakeAsyncPGPool:
            return fake_pool

        stdout = StringIO()
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            with patch("sys.stdout", stdout):
                args = recover_outbox_event._parse_args(
                    ["--outbox-id", "999", "--ticket", "T1", "--json"]
                )
                code = await recover_outbox_event._run_once(_DSN_OK, args)
        assert code == 0
        data = json.loads(stdout.getvalue())
        assert data["eligible"] is False
        assert data["reason_code"] == "outbox_not_found"
        assert data["outbox_id"] == 999


# =========================================================================
# Execute parser
# =========================================================================


class TestExecuteParser:
    def test_execute_without_ticket_or_reason_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            recover_outbox_event._parse_args(
                ["--outbox-id", "1", "--execute", "--yes-i-confirm-recovery"]
            )
        assert exc.value.code == 1

    def test_execute_rejects_operation_id_argument(self) -> None:
        with pytest.raises(SystemExit):
            recover_outbox_event._parse_args(
                ["--outbox-id", "1", "--ticket", "T1",
                 "--execute", "--yes-i-confirm-recovery",
                 "--operation-id", "fake-uuid"]
            )

    def test_requested_by_default_is_none(self) -> None:
        args = recover_outbox_event._parse_args(
            ["--outbox-id", "1", "--ticket", "T1",
             "--execute", "--yes-i-confirm-recovery"]
        )
        assert args.requested_by is None

    def test_requested_by_passed(self) -> None:
        args = recover_outbox_event._parse_args(
            ["--outbox-id", "1", "--ticket", "T1",
             "--execute", "--yes-i-confirm-recovery",
             "--requested-by", "alice"]
        )
        assert args.requested_by == "alice"

    def test_dry_run_still_works_without_execute(self) -> None:
        args = recover_outbox_event._parse_args(
            ["--outbox-id", "1", "--ticket", "T1"]
        )
        assert args.execute is False
        assert args.yes_i_confirm_recovery is False
        assert args.requested_by is None


# =========================================================================
# Execute safety
# =========================================================================


class TestExecuteSafety:
    def test_execute_does_not_import_dispatcher(self) -> None:
        src = Path(recover_outbox_event.__file__).read_text()
        assert "OutboxDispatcher" not in src
        assert "PostgresOutboxStore" not in src
        assert "run_outbox_worker" not in src

    def test_execute_remote_dsn_blocked(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = (
            "postgresql://u:p@db.example.com:5432/events"
        )
        code, _ = recover_outbox_event._check_dsn()
        assert code == 2

    @pytest.mark.asyncio
    async def test_execute_create_pool_failure_returns_4(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK

        async def _boom(*args: Any, **kwargs: Any) -> None:
            raise OSError("connection refused")

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _boom
            code = await recover_outbox_event._run_execute(
                _DSN_OK,
                recover_outbox_event._parse_args([
                    "--outbox-id", "1", "--ticket", "T1",
                    "--execute", "--yes-i-confirm-recovery",
                ]),
            )
        assert code == 4, f"pool failure should return EXIT_QUERY (4), got {code}"

    @pytest.mark.asyncio
    async def test_execute_not_eligible_returns_4(self) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK

        with patch.object(
            recover_outbox_event, "_execute_recovery", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = recover_outbox_event.EXIT_QUERY
            code = await recover_outbox_event._run_execute(
                _DSN_OK,
                recover_outbox_event._parse_args([
                    "--outbox-id", "1", "--ticket", "T1",
                    "--execute", "--yes-i-confirm-recovery",
                ]),
            )
        assert code == 4, f"not eligible should return EXIT_QUERY (4), got {code}"

    def test_dry_run_read_only_preserved(self, fake_pool: FakeAsyncPGPool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK

        async def _fake_create_pool(*args: Any, **kwargs: Any) -> FakeAsyncPGPool:
            return fake_pool

        fake_pool.conn.set_fetchrow_results(
            [{"outbox_id": 1, "event_id": "e1", "event_type": "ConversationMemorySaveRequested",
              "status": "dead_letter", "attempts": 3, "max_attempts": 3},
             {"dlq_id": 1}, None],
        )
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            import argparse
            args = recover_outbox_event._parse_args(["--outbox-id", "1", "--ticket", "T1"])
            code = asyncio.run(recover_outbox_event._run_once(_DSN_OK, args))
        assert code == 0
        all_sql = " ".join(fake_pool.conn.fetched_sql)
        assert "SELECT" in all_sql
        assert "UPDATE" not in all_sql
        assert "INSERT" not in all_sql
        assert "not_eligible" not in all_sql


# =========================================================================
# Structured logs
# =========================================================================


class TestRecoveryDryRunLogs:
    @pytest.mark.asyncio
    async def test_dry_run_started_logged(self, caplog, fake_pool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        caplog.set_level(logging.INFO, logger="recover_outbox_event")
        fake_pool.conn.set_fetchrow_results([
            _OUTBOX_EVENT_DEAD_LETTER,
            {"dlq_id": 1},
            None,
        ])

        async def _fake_create_pool(*a, **kw):
            return fake_pool
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            await recover_outbox_event._run_once(
                _DSN_OK,
                recover_outbox_event._parse_args(
                    ["--outbox-id", "1", "--ticket", "T1"]
                ),
            )
        assert any(
            r.message == "outbox_recovery_dry_run_started"
            for r in caplog.records
        ), "dry_run_started log expected"

    @pytest.mark.asyncio
    async def test_dry_run_finished_logged_eligible(self, caplog, fake_pool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        caplog.set_level(logging.INFO, logger="recover_outbox_event")
        fake_pool.conn.set_fetchrow_results([
            _OUTBOX_EVENT_DEAD_LETTER,
            {"dlq_id": 1},
            None,
        ])

        async def _fake_create_pool(*a, **kw):
            return fake_pool
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            await recover_outbox_event._run_once(
                _DSN_OK,
                recover_outbox_event._parse_args(
                    ["--outbox-id", "1", "--ticket", "T1"]
                ),
            )
        finished = [
            r for r in caplog.records
            if r.message == "outbox_recovery_dry_run_finished"
        ]
        assert len(finished) >= 1
        assert getattr(finished[0], "eligible", None) is True

    @pytest.mark.asyncio
    async def test_dry_run_finished_logged_ineligible(self, caplog, fake_pool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        caplog.set_level(logging.INFO, logger="recover_outbox_event")
        fake_pool.conn.set_fetchrow_results([None])

        async def _fake_create_pool(*a, **kw):
            return fake_pool
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            await recover_outbox_event._run_once(
                _DSN_OK,
                recover_outbox_event._parse_args(
                    ["--outbox-id", "999", "--ticket", "T1"]
                ),
            )
        finished = [
            r for r in caplog.records
            if r.message == "outbox_recovery_dry_run_finished"
        ]
        assert len(finished) >= 1
        assert getattr(finished[0], "eligible", None) is False
        assert getattr(finished[0], "reason_code", None) is not None

    @pytest.mark.asyncio
    async def test_dry_run_finished_includes_duration_ms(self, caplog, fake_pool) -> None:
        os.environ["EVENT_STORE_POSTGRES_DSN"] = _DSN_OK
        caplog.set_level(logging.INFO, logger="recover_outbox_event")
        fake_pool.conn.set_fetchrow_results([
            _OUTBOX_EVENT_DEAD_LETTER,
            {"dlq_id": 1},
            None,
        ])

        async def _fake_create_pool(*a, **kw):
            return fake_pool
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = _fake_create_pool
            await recover_outbox_event._run_once(
                _DSN_OK,
                recover_outbox_event._parse_args(
                    ["--outbox-id", "1", "--ticket", "T1"]
                ),
            )
        finished = [
            r for r in caplog.records
            if r.message == "outbox_recovery_dry_run_finished"
        ]
        assert len(finished) >= 1
        dur = getattr(finished[0], "duration_ms", None)
        assert dur is not None
        assert isinstance(dur, int)
        assert dur >= 0


class TestCorrelationIdInEligibility:
    @pytest.mark.asyncio
    async def test_check_eligibility_returns_correlation_id(self, fake_pool) -> None:
        fake_pool.conn.set_fetchrow_results([
            {
                "outbox_id": 1,
                "event_id": "evt-001",
                "event_type": "ConversationMemorySaveRequested",
                "status": "dead_letter",
                "attempts": 3,
                "max_attempts": 3,
                "correlation_id": "corr-999",
                "causation_id": "cause-888",
            },
            {"dlq_id": 1},
            None,
        ])
        rd = await recover_outbox_event._check_eligibility(
            fake_pool, outbox_id=1, consumer_name="cn", ticket_or_reason="t"
        )
        assert rd["correlation_id"] == "corr-999"
        assert rd["causation_id"] == "cause-888"

    @pytest.mark.asyncio
    async def test_check_eligibility_locked_includes_correlation_id(self, fake_pool) -> None:
        fake_pool.conn.set_fetchrow_results([
            {
                "outbox_id": 1,
                "event_id": "evt-001",
                "event_type": "ConversationMemorySaveRequested",
                "status": "dead_letter",
                "attempts": 3,
                "max_attempts": 3,
                "correlation_id": "corr-111",
                "causation_id": "cause-222",
            },
            {"dlq_id": 1},
            None,
        ])
        rd = await recover_outbox_event._check_eligibility_locked(
            fake_pool.conn, outbox_id=1, consumer_name="cn"
        )
        assert rd["correlation_id"] == "corr-111"
        assert rd["causation_id"] == "cause-222"


class TestRecoverySelectIncludesCorrelationId:
    def test_select_includes_correlation_id_columns(self) -> None:
        src = Path(recover_outbox_event.__file__).read_text()
        assert "correlation_id" in src
        assert "causation_id" in src
        # Verifies that we're not selecting aggregate_id for log
        # (the SELECT must not include aggregate_id)
        # Since we changed _check_eligibility and _check_eligibility_locked,
        # aggregate_id should NOT be in the SELECT
        import re as _re
        select_pattern = _re.findall(
            r"SELECT\s+[\w_,\s]+\s+FROM outbox_events",
            src,
        )
        for select in select_pattern:
            assert "aggregate_id" not in select.split("FROM")[0], (
                f"SELECT must not include aggregate_id: {select}"
            )


# =========================================================================
# Execute output safety
# =========================================================================


class TestExecuteOutputSafety:
    def test_execute_output_safe_keys(self) -> None:
        safe_rd = recover_outbox_event._sanitize_execute_record({
            "executed": True,
            "event_payload": {"secret": "data"},
            "user_message": "should be hidden",
            "assistant_message": "should be hidden",
            "aggregate_id": "conv-abc",
            "conversation_id": "conv-abc",
            "user_id": "u-1",
            "dsn": "postgresql://u:p@127.0.0.1/db",
        })
        assert "executed" in safe_rd
        assert "event_payload" not in safe_rd
        assert "user_message" not in safe_rd
        assert "assistant_message" not in safe_rd
        assert "aggregate_id" not in safe_rd
        assert "conversation_id" not in safe_rd
        assert "user_id" not in safe_rd
        assert "dsn" not in safe_rd

    def test_execute_json_output_has_operation_id(self) -> None:
        from io import StringIO
        rd = {
            "executed": True,
            "eligible": True,
            "outbox_id": 1,
            "event_id": "evt-1",
            "event_type": "ConversationMemorySaveRequested",
            "previous_status": "dead_letter",
            "new_status": "pending",
            "previous_attempts": 3,
            "new_attempts": 0,
            "operation_id": "00000000-0000-0000-0000-000000000001",
            "consumer_name": "cn",
            "reason_code": None,
            "next_step": "run worker or one-shot separately",
        }
        out = StringIO()
        with patch("sys.stdout", out):
            recover_outbox_event._print_execute_json(rd)
        import json as _json
        data = _json.loads(out.getvalue())
        assert data["executed"] is True
        assert data["operation_id"] == "00000000-0000-0000-0000-000000000001"
