#!/usr/bin/env python3
"""Read‑only inspector for outbox_events and outbox_dlq.

Usage:
    python scripts/inspect_outbox.py outbox-pending [--flags]
    python scripts/inspect_outbox.py outbox-locked  [--flags]
    python scripts/inspect_outbox.py outbox-dlq     [--flags]

Exit codes:
    0  OK
    1  Argumentos inválidos
    2  DSN ausente, inválido ou não‑local
    3  Schema / tabela ausente
    4  Erro de conexão ou query
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from app.infrastructure.outbox._cli_shared import (
    COMMAND_TIMEOUT,
    DSN_REGEX,
    POOL_MIN_SIZE,
    POOL_MAX_SIZE,
    redact_dsn as _redact_dsn,
    setup_edd_cli_logging,
)
from app.infrastructure.outbox._error_redaction import sanitize_exception


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ARGS = 1
EXIT_DSN = 2
EXIT_SCHEMA = 3
EXIT_QUERY = 4

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_LIMIT_DEFAULT = 50
BATCH_LIMIT_MAX = 500
ERROR_TRUNCATE_LEN = 200


def _limit_type(val: str) -> int:
    n = int(val)
    if not 1 <= n <= BATCH_LIMIT_MAX:
        raise argparse.ArgumentTypeError(
            f"--limit deve estar entre 1 e {BATCH_LIMIT_MAX}, got {n}"
        )
    return n

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

setup_edd_cli_logging()
logger = logging.getLogger("inspect_outbox")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


class _ArgParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ARGS, f"{self.prog}: error: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgParser(
        description="Inspecionar estado da outbox e DLQ (read‑only).",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    for name in ("outbox-pending", "outbox-locked", "outbox-dlq"):
        p = sub.add_parser(name, help=f"Listar eventos {name.replace('-', ' ')}")
        p.add_argument("--event-type", help="Filtrar por event_type")
        p.add_argument("--since", help="Filtrar a partir da data (ISO 8601, ex.: 2026-07-01)")
        p.add_argument("--outbox-id", type=int, help="Filtrar por outbox_id")
        p.add_argument("--conversation-id", help="Filtrar por aggregate_id (conversation_id técnico)")
        p.add_argument("--limit", type=_limit_type, default=BATCH_LIMIT_DEFAULT,
                        help=f"Máximo de linhas (default: {BATCH_LIMIT_DEFAULT}, max: {BATCH_LIMIT_MAX})")
        p.add_argument("--json", action="store_true", help="Saída em JSON único (em vez de tabela texto)")
        p.add_argument("--show-sanitized-error", action="store_true",
                        help="Exibir last_error/final_error sanitizados (truncado a 200 chars)")
        if name == "outbox-pending":
            p.add_argument("--with-error", action="store_true",
                            help="Exibir apenas pendências que já falharam e ainda podem tentar novamente")

    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _build_parser()
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# DSN gate
# ---------------------------------------------------------------------------


def _check_dsn() -> tuple[int, str | None]:
    dsn = os.environ.get("EVENT_STORE_POSTGRES_DSN")
    if not dsn:
        logger.error("EVENT_STORE_POSTGRES_DSN is not set")
        return EXIT_DSN, None
    if not DSN_REGEX.match(dsn):
        redacted = _redact_dsn(dsn)
        logger.error(
            "DSN inválido ou não‑local (apenas 127.0.0.1 ou localhost): %s",
            redacted,
        )
        return EXIT_DSN, None
    return EXIT_OK, dsn


# ---------------------------------------------------------------------------
# Schema verification
# ---------------------------------------------------------------------------


async def _verify_schema(pool: Any, required: list[str]) -> int:
    async with pool.acquire() as conn:
        for table in required:
            try:
                await conn.execute(f"SELECT 1 FROM {table} LIMIT 0")
            except Exception:
                logger.error(
                    "Schema ausente: tabela %s não encontrada. "
                    "Execute scripts/apply_edd_schema.sh --apply.",
                    table,
                )
                return EXIT_SCHEMA
    return EXIT_OK


# ---------------------------------------------------------------------------
# Query builders — SELECT parametrizado, zero dados sensíveis
# ---------------------------------------------------------------------------


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        raise SystemExit(EXIT_ARGS)


async def _query_pending(
    pool: Any, args: argparse.Namespace
) -> list[dict[str, Any]]:
    since = _parse_since(args.since)
    with_error = getattr(args, "with_error", False)
    limit = args.limit

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT outbox_id, event_id, event_type,
                   attempts, max_attempts,
                   (last_error IS NOT NULL) AS has_error,
                   last_error_class, last_error,
                   created_at, updated_at, available_at,
                   stream_id, aggregate_id
            FROM outbox_events
            WHERE status = 'pending'
              AND ($1::text IS NULL OR event_type = $1)
              AND ($2::timestamptz IS NULL OR available_at >= $2)
              AND ($3::bigint IS NULL OR outbox_id = $3)
              AND ($4::text IS NULL OR aggregate_id = $4)
              AND (NOT $5::boolean OR (last_error IS NOT NULL AND attempts < max_attempts))
            ORDER BY available_at ASC, outbox_id ASC
            LIMIT $6
            """,
            args.event_type,
            since,
            args.outbox_id,
            args.conversation_id,
            with_error,
            limit,
        )
    return [dict(r) for r in rows]


async def _query_locked(
    pool: Any, args: argparse.Namespace
) -> list[dict[str, Any]]:
    since = _parse_since(args.since)
    limit = args.limit

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT outbox_id, event_id, event_type,
                   attempts, locked_by, locked_until, updated_at,
                   stream_id, aggregate_id
            FROM outbox_events
            WHERE status = 'locked'
              AND ($1::text IS NULL OR event_type = $1)
              AND ($2::timestamptz IS NULL OR locked_until >= $2)
              AND ($3::bigint IS NULL OR outbox_id = $3)
              AND ($4::text IS NULL OR aggregate_id = $4)
            ORDER BY locked_until ASC, outbox_id ASC
            LIMIT $5
            """,
            args.event_type,
            since,
            args.outbox_id,
            args.conversation_id,
            limit,
        )
    return [dict(r) for r in rows]


async def _query_dlq(
    pool: Any, args: argparse.Namespace
) -> list[dict[str, Any]]:
    since = _parse_since(args.since)
    limit = args.limit

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT dlq_id, outbox_id, event_id, event_type,
                   attempts, max_attempts,
                   final_error_class, final_error,
                   moved_to_dlq_at, original_created_at,
                   stream_id, aggregate_id, correlation_id, causation_id
            FROM outbox_dlq
            WHERE ($1::text IS NULL OR event_type = $1)
              AND ($2::timestamptz IS NULL OR moved_to_dlq_at >= $2)
              AND ($3::bigint IS NULL OR outbox_id = $3)
              AND ($4::text IS NULL OR aggregate_id = $4)
            ORDER BY moved_to_dlq_at DESC, outbox_id DESC
            LIMIT $5
            """,
            args.event_type,
            since,
            args.outbox_id,
            args.conversation_id,
            limit,
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Formatters — saída texto e JSON, sanitização condicional
# ---------------------------------------------------------------------------

_SENSITIVE_COLUMNS = frozenset({
    "event_payload", "metadata", "user_message", "assistant_message",
    "user_id", "conversation_id",
})


def _sanitize_records(
    records: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    """Remove colunas sensíveis e sanitiza erro se flag ativa."""
    from app.infrastructure.outbox._error_redaction import sanitize_error_message

    cleaned: list[dict[str, Any]] = []
    for row in records:
        safe = {k: v for k, v in row.items() if k not in _SENSITIVE_COLUMNS}
        if args.show_sanitized_error:
            for err_col in ("last_error", "final_error"):
                if err_col in safe and safe[err_col] is not None:
                    safe[err_col] = sanitize_error_message(
                        str(safe[err_col]), max_length=ERROR_TRUNCATE_LEN
                    )
        else:
            safe.pop("last_error", None)
            safe.pop("final_error", None)
        cleaned.append(safe)
    return cleaned


def _fmt(val: Any) -> str:
    """Format a value for text table display."""
    if val is None:
        return "—"
    if isinstance(val, datetime):
        return val.isoformat(timespec="seconds")
    if isinstance(val, bool):
        return "sim" if val else "não"
    return str(val)


def _print_text_table(
    records: list[dict[str, Any]],
    args: argparse.Namespace,
    dsn: str,
) -> None:
    """Print a header block then a simple text table to stdout."""
    from datetime import timezone as tz

    now_utc = datetime.now(tz.utc).isoformat(timespec="seconds")
    print(f"[{now_utc}]")
    print(f"dsn:         {_redact_dsn(dsn)}")
    print(f"command:     {args.subcommand}")
    filters_parts = []
    if args.event_type:
        filters_parts.append(f"event_type={args.event_type}")
    if args.since:
        filters_parts.append(f"since={args.since}")
    if args.outbox_id:
        filters_parts.append(f"outbox_id={args.outbox_id}")
    if args.conversation_id:
        filters_parts.append(f"conversation_id={args.conversation_id}")
    if getattr(args, "with_error", False):
        filters_parts.append("with_error=sim")
    print(f"filters:     {', '.join(filters_parts) if filters_parts else '—'}")
    print(f"limit:       {args.limit}")
    print(f"count:       {len(records)}")
    print()

    if not records:
        print("(sem registros)")
        return

    # Build column list dynamically from first record
    keys = list(records[0].keys())
    col_widths = {k: max(len(k), max((len(_fmt(r[k])) for r in records), default=0)) for k in keys}
    sep = "  "

    header = sep.join(k.ljust(col_widths[k]) for k in keys)
    print(header)
    print("-" * len(header))
    for row in records:
        line = sep.join(_fmt(row[k]).ljust(col_widths[k]) for k in keys)
        print(line)
    print()


def _print_json(
    records: list[dict[str, Any]],
    args: argparse.Namespace,
    dsn: str,
) -> None:
    """Print a single JSON object with metadata to stdout."""
    output = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": args.subcommand,
        "filters": {
            "event_type": args.event_type,
            "since": args.since,
            "outbox_id": args.outbox_id,
            "conversation_id": args.conversation_id,
            "with_error": getattr(args, "with_error", False),
        },
        "limit": args.limit,
        "count": len(records),
        "items": records,
    }
    json.dump(output, sys.stdout, default=str, ensure_ascii=False)
    sys.stdout.write("\n")


def _format_and_print(
    records: list[dict[str, Any]],
    args: argparse.Namespace,
    dsn: str,
) -> None:
    safe = _sanitize_records(records, args)
    if args.json:
        _print_json(safe, args, dsn)
    else:
        _print_text_table(safe, args, dsn)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run_once(dsn: str, args: argparse.Namespace) -> int:
    import asyncpg

    t0 = time.monotonic()

    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            command_timeout=COMMAND_TIMEOUT,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "outbox_inspect_failed",
            extra={
                "command": args.subcommand,
                "attempted_action": "pool_create",
                "error_class": exc.__class__.__name__,
                "sanitized_error": sanitize_exception(exc, max_length=200),
                "duration_ms": duration_ms,
            },
        )
        return EXIT_QUERY

    async with pool:
        tables = {
            "outbox-pending": ["outbox_events"],
            "outbox-locked": ["outbox_events"],
            "outbox-dlq": ["outbox_events", "outbox_dlq"],
        }
        schema_code = await _verify_schema(pool, tables[args.subcommand])
        if schema_code != EXIT_OK:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "outbox_inspect_failed",
                extra={
                    "command": args.subcommand,
                    "attempted_action": "schema_check",
                    "sanitized_error": f"exit_code={schema_code}",
                    "duration_ms": duration_ms,
                },
            )
            return schema_code

        logger.info(
            "outbox_inspect_started",
            extra={
                "command": args.subcommand,
                "event_type": args.event_type,
                "since": args.since,
                "outbox_id": args.outbox_id,
                "limit": args.limit,
            },
        )

        queries = {
            "outbox-pending": _query_pending,
            "outbox-locked": _query_locked,
            "outbox-dlq": _query_dlq,
        }
        try:
            records = await queries[args.subcommand](pool, args)
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "outbox_inspect_failed",
                extra={
                    "command": args.subcommand,
                    "attempted_action": "query",
                    "error_class": exc.__class__.__name__,
                    "sanitized_error": sanitize_exception(exc, max_length=200),
                    "duration_ms": duration_ms,
                },
            )
            return EXIT_QUERY

    duration_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "outbox_inspect_finished",
        extra={
            "command": args.subcommand,
            "count": len(records),
            "duration_ms": duration_ms,
        },
    )
    _format_and_print(records, args, dsn)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn_code, dsn = _check_dsn()
    if dsn_code != EXIT_OK:
        return dsn_code
    return asyncio.run(_run_once(dsn, args))  # type: ignore[arg-type]


def entry_point() -> NoReturn:
    sys.exit(main())


if __name__ == "__main__":
    entry_point()
