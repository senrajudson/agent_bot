"""Tests for event_store exports — TransactionalPostgresEventStore is importable."""
from __future__ import annotations


class TestEventStoreExports:
    """T7: exports from app.infrastructure.event_store package."""

    def test_transactional_postgres_event_store_is_exported(self) -> None:
        from app.infrastructure.event_store import TransactionalPostgresEventStore
        assert TransactionalPostgresEventStore is not None

    def test_event_store_exports_unchanged_for_legacy(self) -> None:
        from app.infrastructure.event_store import (
            EventStore,
            EventPublisher,
            InMemoryEventStore,
            PostgresEventStore,
            RedisStreamsEventStore,
        )
        for cls in (EventStore, EventPublisher, InMemoryEventStore,
                     PostgresEventStore, RedisStreamsEventStore):
            assert cls is not None

    def test_event_store_all_contains_transactional_postgres(self) -> None:
        import app.infrastructure.event_store as pkg
        assert "TransactionalPostgresEventStore" in pkg.__all__
