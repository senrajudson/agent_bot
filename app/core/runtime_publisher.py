"""Runtime Event Publisher — builds EventPublisher from pool and settings.

This module is an isolated, pure, synchronous helper that prepares the
future activation of the /chat endpoint with a transactional Postgres
EventStore.  It is NOT connected to /chat in this cycle.

Design decisions (EDD Prompt 9 / D1–D20):
- Fallback is always NullEventPublisher, never InMemoryEventStore.
- The helper is tolerant; the lifecycle remains fail-fast.
- No I/O, no async, no pool creation, no FastAPI dependency.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.application.sagas.event_publisher import EventPublisherImpl
from app.application.sagas.event_publisher import NullEventPublisher
from app.core.config import Settings
from app.core.config import settings as _global_settings
from app.infrastructure.event_store import EventPublisher
from app.infrastructure.event_store import TransactionalPostgresEventStore

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("app.core.runtime_publisher")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_TRUNCATE_LIMIT: int = 500

TRANSACTIONAL_BACKEND: str = "transactional_postgres"
TRANSACTIONAL_PUBLISHER_TYPE: str = "EventPublisherImpl"
TRANSACTIONAL_STORE_TYPE: str = "TransactionalPostgresEventStore"
NULL_PUBLISHER_TYPE: str = "NullEventPublisher"

EVENT_DISABLED: str = "event_publisher_disabled"
EVENT_FALLBACK_NULL: str = "event_publisher_fallback_null"
EVENT_CREATED_TX: str = "event_publisher_created_transactional"
EVENT_CREATION_FAILED: str = "event_publisher_creation_failed"

REASON_BACKEND_MISMATCH: str = "backend_mismatch"
REASON_POOL_MISSING: str = "pool_missing"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(value: str, limit: int = LOG_TRUNCATE_LIMIT) -> str:
    """Truncate *value* to *limit* characters, appending ``'...'`` when cut."""
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def _redact_dsn(value: str) -> str:
    """Replace DSN-like patterns with a placeholder to avoid secret leakage.

    Matches e.g. ``postgresql://user:password@host:port/db``.
    """
    return re.sub(r"[a-z]+://[^\s]+", "[DSN_REDACTED]", value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_runtime_event_publisher(
    pool: Any | None,
    settings: Settings | None = None,
) -> EventPublisher:
    """Build an ``EventPublisher`` from an asyncpg pool and application settings.

    Five decision branches (R1–R5):

    R1 — ``EVENT_DRIVEN_ENABLED=false``:
        Returns ``NullEventPublisher``.  No pool, no store.
    R2 — backend is not ``transactional_postgres``:
        Returns ``NullEventPublisher`` with a ``backend_mismatch`` log.
    R3 — pool is ``None``:
        Returns ``NullEventPublisher`` with a ``pool_missing`` log.
    R4 — all pre-requisites satisfied:
        Returns ``EventPublisherImpl(TransactionalPostgresEventStore(pool))``.
    R5 — unexpected exception during R4:
        Returns ``NullEventPublisher`` with a truncated error log.

    The function is **pure** (deterministic, no I/O, no ``await``) and
    **never raises** — all exceptions are caught in R5.
    """
    s = settings if settings is not None else _global_settings

    # -- R1: flag false ---------------------------------------------------
    if not s.EVENT_DRIVEN_ENABLED:
        logger.info(
            "event=%s enabled=false publisher_type=%s",
            EVENT_DISABLED,
            NULL_PUBLISHER_TYPE,
        )
        return NullEventPublisher()

    # -- R2: backend mismatch ---------------------------------------------
    if s.EVENT_STORE_BACKEND != TRANSACTIONAL_BACKEND:
        logger.info(
            "event=%s reason=%s enabled=true backend=%s publisher_type=%s",
            EVENT_FALLBACK_NULL,
            REASON_BACKEND_MISMATCH,
            s.EVENT_STORE_BACKEND,
            NULL_PUBLISHER_TYPE,
        )
        return NullEventPublisher()

    # -- R3: pool missing -------------------------------------------------
    if pool is None:
        logger.info(
            "event=%s reason=%s enabled=true backend=%s publisher_type=%s",
            EVENT_FALLBACK_NULL,
            REASON_POOL_MISSING,
            TRANSACTIONAL_BACKEND,
            NULL_PUBLISHER_TYPE,
        )
        return NullEventPublisher()

    # -- R4: success (transactional) --------------------------------------
    try:
        store = TransactionalPostgresEventStore(pool=pool)
        publisher: EventPublisher = EventPublisherImpl(event_store=store)
    except Exception as exc:
        # -- R5: unexpected error during R4 --------------------------------
        _redacted = _redact_dsn(str(exc))
        logger.warning(
            "event=%s error_class=%s error_message_truncated=%s "
            "publisher_type=%s",
            EVENT_CREATION_FAILED,
            type(exc).__name__,
            _truncate(_redacted),
            NULL_PUBLISHER_TYPE,
        )
        return NullEventPublisher()

    logger.info(
        "event=%s enabled=true backend=%s publisher_type=%s store_type=%s",
        EVENT_CREATED_TX,
        TRANSACTIONAL_BACKEND,
        TRANSACTIONAL_PUBLISHER_TYPE,
        TRANSACTIONAL_STORE_TYPE,
    )
    return publisher
