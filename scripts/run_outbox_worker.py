#!/usr/bin/env python3
"""Worker contínuo controlado para OutboxDispatcher.

Consome ``outbox_events`` em loop chamando ``OutboxDispatcher.dispatch_once()``,
com gates fortes, shutdown limpo, logs seguros e sem fallback LoggingOutboxConsumer.

Local/QA only neste ciclo.
Recovery executável permanece bloqueado (Prompt 22 — decisão documentada).

Gates obrigatórios:
    OUTBOX_WORKER_ENABLED=true
    EVENT_DRIVEN_ENABLED=true
    EVENT_STORE_POSTGRES_DSN  (apenas 127.0.0.1 ou localhost)

Usage:
    python scripts/run_outbox_worker.py --max-iterations 1
    python scripts/run_outbox_worker.py --batch-size 10 --interval-seconds 5

Exit codes:
    0  Sucesso / shutdown limpo / max_iterations concluído
    1  Argumentos inválidos
    2  Gate / DSN / config inválido
    3  Schema / config operacional ausente
    5  Startup failure inesperado
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import signal
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any, NoReturn

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import asyncpg

from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxDispatcher,
    OutboxEvent,
    PostgresOutboxStore,
)
from app.infrastructure.outbox.event_type_router_consumer import (
    EventTypeRouterConsumer,
)
from app.infrastructure.outbox._cli_shared import (
    COMMAND_TIMEOUT,
    DSN_REGEX,
    POOL_MIN_SIZE,
    POOL_MAX_SIZE,
    redact_dsn as _redact_dsn,
    setup_edd_cli_logging,
)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ARGS = 1
EXIT_GATE = 2
EXIT_CONFIG = 3
EXIT_STARTUP = 5

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE_DEFAULT = 10
INTERVAL_SECONDS_DEFAULT = 5.0
BACKOFF_BASE_DEFAULT = 1.0
BACKOFF_MAX_DEFAULT = 30.0
JITTER_DEFAULT = 0.0
CONSUMER_NAME_DEFAULT = "outbox-conversation-memory-save-v1"

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

setup_edd_cli_logging()
logger = logging.getLogger("run_outbox_worker")


def _dsn_host_for_log(dsn: str) -> str:
    """Extract a safe host:port fragment from a Postgres DSN (no credentials)."""
    if not dsn or "@" not in dsn:
        return "unknown"
    try:
        return dsn.split("@", 1)[-1].split("/", 1)[0]
    except Exception:
        return "unknown"


def _resolve_worker_id(explicit: str | None) -> str:
    """Return explicit worker id or auto-generate from hostname + uuid8."""
    if explicit:
        return explicit
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return f"{host}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Argparse custom types
# ---------------------------------------------------------------------------


def _positive_int(val: str) -> int:
    n = int(val)
    if n <= 0:
        raise argparse.ArgumentTypeError(
            f"must be a positive integer, got {val}"
        )
    return n


def _non_negative_float(val: str) -> float:
    f = float(val)
    if f < 0:
        raise argparse.ArgumentTypeError(
            f"must be >= 0, got {val}"
        )
    return f


def _positive_int_or_none(val: str) -> int | None:
    if val.lower() in ("none", "null", ""):
        return None
    n = int(val)
    if n <= 0:
        raise argparse.ArgumentTypeError(
            f"must be > 0 or None/omitido, got {val}"
        )
    return n


def _non_empty_str(val: str) -> str:
    if not val or not val.strip():
        raise argparse.ArgumentTypeError("must not be empty")
    return val


_CONSUMER_NAME_REGEX = re.compile(
    r"^outbox-[a-z][a-z0-9-]{0,30}-v[0-9]+$"
)


def _valid_consumer_name(val: str) -> str:
    if not _CONSUMER_NAME_REGEX.match(val):
        raise argparse.ArgumentTypeError(
            f"invalid consumer name format: {val!r}"
        )
    return val


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


class _ArgParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ARGS, f"{self.prog}: error: {message}\n")


def _build_parser() -> _ArgParser:
    parser = _ArgParser(
        description=(
            "Worker contínuo controlado para OutboxDispatcher "
            "(local/QA only)."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=BATCH_SIZE_DEFAULT,
        help=f"Número máximo de eventos por batch (default: {BATCH_SIZE_DEFAULT})",
    )
    parser.add_argument(
        "--interval-seconds",
        type=_non_negative_float,
        default=INTERVAL_SECONDS_DEFAULT,
        help=f"Sleep entre iterações quando vazio (default: {INTERVAL_SECONDS_DEFAULT})",
    )
    parser.add_argument(
        "--max-iterations",
        type=_positive_int_or_none,
        default=None,
        help="Máximo de iterações do loop (omitido = infinito)",
    )
    parser.add_argument(
        "--backoff-base-seconds",
        type=_non_negative_float,
        default=BACKOFF_BASE_DEFAULT,
        help=f"Base de backoff exponencial (default: {BACKOFF_BASE_DEFAULT})",
    )
    parser.add_argument(
        "--backoff-max-seconds",
        type=_non_negative_float,
        default=BACKOFF_MAX_DEFAULT,
        help=f"Teto do backoff exponencial (default: {BACKOFF_MAX_DEFAULT})",
    )
    parser.add_argument(
        "--jitter-seconds",
        type=_non_negative_float,
        default=JITTER_DEFAULT,
        help=f"Jitter uniforme somado ao sleep (default: {JITTER_DEFAULT})",
    )
    parser.add_argument(
        "--consumer-name",
        type=_valid_consumer_name,
        default=CONSUMER_NAME_DEFAULT,
        help=(
            f"Identificador do consumer "
            f"(default: {CONSUMER_NAME_DEFAULT})"
        ),
    )
    parser.add_argument(
        "--worker-id",
        type=_non_empty_str,
        default=None,
        help="Identificador do worker (default: auto-gerado)",
    )
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _build_parser()
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Gate checks
# ---------------------------------------------------------------------------


def _check_outbox_worker_enabled() -> int:
    """Gate 1: OUTBOX_WORKER_ENABLED must be 'true'."""
    enabled = os.environ.get("OUTBOX_WORKER_ENABLED", "").lower()
    if enabled != "true":
        logger.error(
            "Gate bloqueado: OUTBOX_WORKER_ENABLED must be 'true', got %r",
            enabled,
        )
        return EXIT_GATE
    return EXIT_OK


def _check_event_driven_enabled() -> int:
    """Gate 2: EVENT_DRIVEN_ENABLED must be 'true'."""
    enabled = os.environ.get("EVENT_DRIVEN_ENABLED", "").lower()
    if enabled != "true":
        logger.error(
            "Gate bloqueado: EVENT_DRIVEN_ENABLED must be 'true', got %r",
            enabled,
        )
        return EXIT_GATE
    return EXIT_OK


def _check_dsn() -> tuple[int, str | None]:
    """Gate 3: EVENT_STORE_POSTGRES_DSN must be set and local-only."""
    dsn = os.environ.get("EVENT_STORE_POSTGRES_DSN")
    if not dsn:
        logger.error("Gate bloqueado: EVENT_STORE_POSTGRES_DSN is not set")
        return EXIT_GATE, None
    if not DSN_REGEX.match(dsn):
        redacted = _redact_dsn(dsn)
        logger.error(
            "Gate bloqueado: DSN inválido ou não‑local (apenas 127.0.0.1 "
            "ou localhost): %s",
            redacted,
        )
        return EXIT_GATE, None
    return EXIT_OK, dsn


# ---------------------------------------------------------------------------
# FailingOutboxConsumer — fallback seguro (worker-local)
# ---------------------------------------------------------------------------


class FailingOutboxConsumer:
    """Fallback seguro para event_type sem handler registrado.

    Substitui LoggingOutboxConsumer como fallback em worker contínuo.
    LoggingOutboxConsumer mascararia o problema; FailingOutboxConsumer
    força o dispatcher a tratar como falha retentável → DLQ após max_attempts.
    """

    def __init__(self) -> None:
        self._consumer_name = "outbox-worker-failing-fallback"

    async def handle(self, event: OutboxEvent) -> None:
        raise RuntimeError(
            f"no handler registered for event_type={event.event_type!r}; "
            f"event_id={event.event_id} outbox_id={event.outbox_id}"
        )


# ---------------------------------------------------------------------------
# Consumer builder
# ---------------------------------------------------------------------------


def _build_consumer() -> EventTypeRouterConsumer:
    """Build EventTypeRouterConsumer with ConversationMemorySaveRequested handler.

    Only ``ConversationMemorySaveRequested`` is registered.  Any other
    ``event_type`` reaches ``FailingOutboxConsumer`` which raises
    ``RuntimeError`` → the dispatcher treats it as a retryable failure
    → after ``max_attempts`` the event goes to ``outbox_dlq``.
    """
    from app.infrastructure.outbox.handlers.conversation_memory_save_handler import (
        ConversationMemorySaveOutboxHandler,
        SaveConversationTurnMemorySaver,
    )
    from app.application.commands.save_conversation_turn import (
        SaveConversationTurnHandler,
    )
    from app.services.chat_memory_service import (
        append_memory_turns,
        format_memory_for_prompt,
        load_memory_turns,
    )
    from app.domain.value_objects import ConversationId

    class _MemoryAdapter:
        async def append_turns(
            self,
            conversation_id: Any,
            user_message: str,
            assistant_message: str,
            metadata: dict | None = None,
            *,
            idempotency_key: str | None = None,
        ) -> None:
            cid = (
                str(conversation_id)
                if isinstance(conversation_id, ConversationId)
                else conversation_id
            )
            await append_memory_turns(
                cid,
                user_message,
                assistant_message,
                metadata,
                idempotency_key=idempotency_key,
            )

        async def load_turns(
            self,
            conversation_id: Any,
            max_turns: int | None = None,
        ) -> list:
            cid = (
                str(conversation_id)
                if isinstance(conversation_id, ConversationId)
                else conversation_id
            )
            return await load_memory_turns(cid, max_turns)

        def format_for_prompt(self, turns: list) -> str:
            return format_memory_for_prompt(turns)

    save_handler = SaveConversationTurnHandler(memory=_MemoryAdapter())
    saver = SaveConversationTurnMemorySaver(save_handler)
    handler = ConversationMemorySaveOutboxHandler(saver=saver)

    return EventTypeRouterConsumer(
        handlers={"ConversationMemorySaveRequested": handler},
        fallback=FailingOutboxConsumer(),
    )


# ---------------------------------------------------------------------------
# Dispatcher builder
# ---------------------------------------------------------------------------


def _build_dispatcher(
    pool: asyncpg.Pool,
    consumer: EventTypeRouterConsumer,
    args: argparse.Namespace,
) -> OutboxDispatcher:
    """Build an OutboxDispatcher with the given pool, consumer and args."""
    return OutboxDispatcher(
        store=PostgresOutboxStore(pool=pool),
        consumer=consumer,
        consumer_name=args.consumer_name,
        worker_id=_resolve_worker_id(args.worker_id),
        batch_size=args.batch_size,
    )


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


def _install_signal_handlers(
    shutdown_event: asyncio.Event, loop: asyncio.AbstractEventLoop
) -> None:
    """Register SIGINT/SIGTERM handlers that set ``shutdown_event``."""

    def _handler(signame: str) -> None:
        if shutdown_event.is_set():
            logger.warning(
                "outbox_worker_shutdown_double_signal",
                extra={"signal": signame},
            )
            return
        logger.info(
            "outbox_worker_shutdown_signal",
            extra={"signal": signame},
        )
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handler, sig.name)
        except (NotImplementedError, RuntimeError):
            logger.warning(
                "outbox_worker_signal_handler_unavailable",
                extra={"signal": sig.name},
            )


# ---------------------------------------------------------------------------
# Schema check
# ---------------------------------------------------------------------------


async def _verify_schema(pool: asyncpg.Pool) -> int:
    """Verify that ``outbox_events`` exists.  Returns EXIT_CONFIG if missing."""
    async with pool.acquire() as conn:
        try:
            await conn.execute("SELECT 1 FROM outbox_events LIMIT 0")
        except asyncpg.UndefinedTableError:
            logger.error(
                "Schema ausente: tabela outbox_events não encontrada. "
                "Execute scripts/apply_edd_schema.sh --apply."
            )
            return EXIT_CONFIG
        except asyncpg.PostgresError as exc:
            from app.infrastructure.outbox._error_redaction import (
                sanitize_error_message,
            )
            logger.error(
                "Erro de configuração do banco: %s",
                sanitize_error_message(str(exc)),
            )
            return EXIT_CONFIG
    return EXIT_OK


# ---------------------------------------------------------------------------
# Sleep / shutdown helper
# ---------------------------------------------------------------------------


async def _sleep_or_shutdown(
    seconds: float, shutdown_event: asyncio.Event
) -> bool:
    """Sleep ``seconds`` or until ``shutdown_event`` is set.

    Returns ``False`` if shutdown occurred mid-sleep.
    """
    if seconds <= 0:
        return True
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return True
    return False


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


async def _run_loop(
    dispatcher: OutboxDispatcher,
    args: argparse.Namespace,
    shutdown_event: asyncio.Event,
) -> int:
    """Run ``dispatcher.dispatch_once()`` in a controlled loop."""
    from app.infrastructure.outbox._error_redaction import sanitize_exception
    from app.infrastructure.outbox.outbox_dispatcher import (
        OutboxDispatchResult,
    )

    iteration = 0
    consecutive_errors = 0
    total_claimed = 0
    total_processed = 0
    total_dlq = 0

    while not shutdown_event.is_set():
        if args.max_iterations is not None and iteration >= args.max_iterations:
            break
        iteration += 1

        try:
            t_iter = time.monotonic()
            result: OutboxDispatchResult = await dispatcher.dispatch_once()
            consecutive_errors = 0
            total_claimed += result.claimed_count
            total_processed += result.processed_count
            total_dlq += result.dlq_count
            iter_duration_ms = int((time.monotonic() - t_iter) * 1000)

            if result.claimed_count == 0:
                logger.info(
                    "outbox_worker_idle",
                    extra={
                        "iteration": iteration,
                        "sleep_seconds": args.interval_seconds,
                    },
                )
                if not await _sleep_or_shutdown(
                    args.interval_seconds + args.jitter_seconds,
                    shutdown_event,
                ):
                    break
            else:
                logger.info(
                    "outbox_worker_iteration",
                    extra={
                        "iteration": iteration,
                        "claimed_count": result.claimed_count,
                        "processed_count": result.processed_count,
                        "already_processed_count": (
                            result.already_processed_count
                        ),
                        "dispatched_count": result.dispatched_count,
                        "retry_count": result.retry_count,
                        "dlq_count": result.dlq_count,
                        "duration_ms": iter_duration_ms,
                    },
                )
                if args.max_iterations is None or iteration < args.max_iterations:
                    if not await _sleep_or_shutdown(
                        args.interval_seconds + args.jitter_seconds,
                        shutdown_event,
                    ):
                        break
        except Exception as exc:
            consecutive_errors += 1
            backoff_seconds = min(
                args.backoff_base_seconds * (2 ** (consecutive_errors - 1)),
                args.backoff_max_seconds,
            )
            logger.warning(
                "outbox_worker_error",
                extra={
                    "iteration": iteration,
                    "error_class": exc.__class__.__name__,
                    "sanitized_error": sanitize_exception(
                        exc, max_length=512
                    ),
                    "backoff_seconds": backoff_seconds,
                },
            )
            if args.max_iterations is None or iteration < args.max_iterations:
                if not await _sleep_or_shutdown(
                    backoff_seconds, shutdown_event
                ):
                    break

    logger.info(
        "outbox_worker_stopped",
        extra={
            "total_iterations": iteration,
            "total_claimed": total_claimed,
            "total_processed": total_processed,
            "total_dlq": total_dlq,
        },
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


async def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return exc.code

    # -- Gate 1 --
    if (code := _check_outbox_worker_enabled()) != EXIT_OK:
        return code

    # -- Gate 2 --
    if (code := _check_event_driven_enabled()) != EXIT_OK:
        return code

    # -- Gate 3 --
    code, dsn = _check_dsn()
    if code != EXIT_OK:
        return code

    dsn_host = _dsn_host_for_log(dsn)
    worker_id = _resolve_worker_id(args.worker_id)

    logger.info(
        "outbox_worker_starting",
        extra={
            "batch_size": args.batch_size,
            "interval_seconds": args.interval_seconds,
            "max_iterations": args.max_iterations,
            "backoff_base_seconds": args.backoff_base_seconds,
            "backoff_max_seconds": args.backoff_max_seconds,
            "jitter_seconds": args.jitter_seconds,
            "consumer_name": args.consumer_name,
            "worker_id": worker_id,
            "dsn_host": dsn_host,
        },
    )

    # -- Pool --
    pool: asyncpg.Pool | None = None
    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            command_timeout=COMMAND_TIMEOUT,
        )
    except Exception as exc:
        from app.infrastructure.outbox._error_redaction import (
            sanitize_error_message,
        )
        logger.error(
            "Falha ao criar pool asyncpg: %s",
            sanitize_error_message(str(exc)),
        )
        return EXIT_STARTUP

    # -- Schema check --
    if (code := await _verify_schema(pool)) != EXIT_OK:
        return code

    try:
        consumer = _build_consumer()
        dispatcher = _build_dispatcher(pool, consumer, args)

        logger.info(
            "outbox_worker_started",
            extra={
                "worker_id": worker_id,
                "consumer_name": args.consumer_name,
                "dsn_host": dsn_host,
            },
        )

        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        _install_signal_handlers(shutdown_event, loop)

        exit_code = await _run_loop(dispatcher, args, shutdown_event)
        logger.info(
            "outbox_worker_shutdown",
            extra={"reason": "loop_exit"},
        )
        return exit_code
    except Exception as exc:
        from app.infrastructure.outbox._error_redaction import (
            sanitize_error_message,
            sanitize_exception,
        )
        logger.warning(
            "outbox_worker_shutdown",
            extra={
                "reason": "exception",
                "error_class": exc.__class__.__name__,
                "sanitized_error": sanitize_exception(exc, max_length=512),
            },
        )
        return EXIT_OK
    finally:
        if pool is not None:
            try:
                await pool.close()
            except Exception as exc:
                from app.infrastructure.outbox._error_redaction import (
                    sanitize_error_message,
                )
                logger.warning(
                    "outbox_worker_pool_close_failed",
                    extra={
                        "error_class": exc.__class__.__name__,
                        "sanitized_error": sanitize_exception(exc, max_length=512),
                    },
                )


def _sync_main(argv: list[str] | None = None) -> int:
    return asyncio.run(main(argv))


def entry_point() -> NoReturn:
    sys.exit(_sync_main())


if __name__ == "__main__":
    entry_point()
