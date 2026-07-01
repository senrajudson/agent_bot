"""Event-Driven Design lifecycle — gated asyncpg pool for FastAPI.

Creates and closes an ``asyncpg`` pool at startup/shutdown only when:
- ``EVENT_DRIVEN_ENABLED=true`` AND
- ``EVENT_STORE_BACKEND=transactional_postgres`` AND
- ``EVENT_STORE_POSTGRES_DSN`` is present.

In any other combination the lifespan is a no-op (G0) or fail-fast (G1/G2).

The pool is stored in ``app.state.postgres_pool``.  ``/chat`` and
``process_message`` are NOT modified in this module.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg
from fastapi import FastAPI

from app.core.config import settings

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENT_DRIVEN_BACKEND: str = "transactional_postgres"
MAX_ERROR_MESSAGE_LENGTH: int = 500


# ---------------------------------------------------------------------------
# Helpers — pure, no I/O
# ---------------------------------------------------------------------------


def build_event_store_pool_kwargs(settings: Any) -> dict[str, object]:
    """Return fixed kwargs for ``asyncpg.create_pool``.

    Pure function — always returns the same dict for any valid ``Settings``.
    """
    return {"min_size": 1, "max_size": 4, "command_timeout": 30}


def _truncate(value: str, limit: int = MAX_ERROR_MESSAGE_LENGTH) -> str:
    """Truncate *value* to *limit* characters, appending ``'...'`` when cut."""
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def _dsn_host_for_log(dsn: str) -> str:
    """Extract a safe host/port fragment from a Postgres DSN for logging.

    Never returns user, password or full DSN.  Returns ``'unknown'`` on
    failure.  Equivalent to ``_mask_dsn_host`` in
    ``app.infrastructure.event_store.factory`` but kept local to avoid
    coupling the lifecycle module to the infrastructure layer.
    """
    if not dsn or "@" not in dsn:
        return "unknown"
    try:
        return dsn.split("@", 1)[-1].split("/", 1)[0]
    except Exception:  # noqa: BLE001
        return "unknown"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def event_driven_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan that gates pool creation behind two env vars.

    Gates
    -----
    G0: ``EVENT_DRIVEN_ENABLED=false`` → no-op.
    G1: flag true + wrong backend  → ``ValueError`` (fail-fast).
    G2: flag true + DSN missing    → ``ValueError`` (fail-fast).
    G3: flag true + correct DSN    → create pool, yield, close.
    """

    # -- G0: flag off → no-op --
    if not settings.EVENT_DRIVEN_ENABLED:
        logger.info("EventStore EDD: pool disabled (EVENT_DRIVEN_ENABLED=false)")
        yield
        return

    # -- G1: wrong backend → fail-fast --
    if settings.EVENT_STORE_BACKEND != EVENT_DRIVEN_BACKEND:
        raise ValueError(
            f"EVENT_STORE_BACKEND must be {EVENT_DRIVEN_BACKEND!r} when "
            f"EVENT_DRIVEN_ENABLED is true; got {settings.EVENT_STORE_BACKEND!r}"
        )

    # -- G2: DSN missing → fail-fast --
    dsn: str | None = settings.EVENT_STORE_POSTGRES_DSN
    if not dsn:
        raise ValueError(
            "EVENT_STORE_POSTGRES_DSN is required when EVENT_DRIVEN_ENABLED is true"
        )

    # -- G3: create pool --
    pool_kwargs = build_event_store_pool_kwargs(settings)
    logger.info(
        "EventStore EDD: pool startup requested (backend=%s, kwargs=%s)",
        settings.EVENT_STORE_BACKEND,
        pool_kwargs,
    )

    try:
        pool = await asyncpg.create_pool(dsn, **pool_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "EventStore EDD: pool startup failed "
            "(error_class=%s, error_message=%s, dsn_host=%s, backend=%s, kwargs=%s)",
            type(exc).__name__,
            _truncate(str(exc)),
            _dsn_host_for_log(dsn),
            settings.EVENT_STORE_BACKEND,
            pool_kwargs,
        )
        raise

    app.state.postgres_pool = pool  # type: ignore[attr-defined]
    logger.info(
        "EventStore EDD: pool created (min_size=%s, max_size=%s)",
        pool_kwargs["min_size"],
        pool_kwargs["max_size"],
    )

    try:
        yield
    finally:
        logger.info("EventStore EDD: pool closing")
        try:
            await pool.close()
            logger.info("EventStore EDD: pool closed")
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "EventStore EDD: pool close failed "
                "(error_class=%s, error_message=%s)",
                type(exc).__name__,
                _truncate(str(exc)),
            )
