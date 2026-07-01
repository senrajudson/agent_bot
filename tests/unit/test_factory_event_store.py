"""Tests for get_transactional_event_store (T8) and get_event_store legacy (T9)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.infrastructure.event_store.transactional_postgres_event_store import TransactionalPostgresEventStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ENV = {
    "EVENT_DRIVEN_ENABLED": "true",
    "EVENT_STORE_BACKEND": "transactional_postgres",
    "EVENT_STORE_POSTGRES_DSN": "postgresql://user:pwd@host:5432/db",
}


def _make_settings(**overrides: str) -> Settings:
    """Build a Settings with EDD env set. Accepts optional overrides."""
    env = {**_VALID_ENV, **overrides}
    import os
    for k, v in env.items():
        os.environ[k] = v
    try:
        return Settings()
    finally:
        for k in env:
            os.environ.pop(k, None)


def _fake_pool() -> MagicMock:
    return MagicMock(name="fake_pool")


# ---------------------------------------------------------------------------
# T8 — Tests for get_transactional_event_store
# ---------------------------------------------------------------------------


class TestGetTransactionalEventStoreSuccess:
    """T8: happy path."""

    def test_returns_transactional_postgres_event_store(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings()
        pool = _fake_pool()
        store = get_transactional_event_store(pool=pool, settings=s)
        assert isinstance(store, TransactionalPostgresEventStore)

    def test_preserves_pool_reference(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings()
        pool = _fake_pool()
        store = get_transactional_event_store(pool=pool, settings=s)
        assert store._pool is pool


class TestGetTransactionalEventStoreFailures:
    """T8: all validation failure paths."""

    def test_fails_when_flag_false(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings(EVENT_DRIVEN_ENABLED="false")
        with pytest.raises(ValueError, match="EVENT_DRIVEN_ENABLED must be true"):
            get_transactional_event_store(pool=_fake_pool(), settings=s)

    def test_fails_when_backend_memory(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings(EVENT_STORE_BACKEND="memory")
        with pytest.raises(ValueError, match="must be 'transactional_postgres'.*got 'memory'"):
            get_transactional_event_store(pool=_fake_pool(), settings=s)

    def test_fails_when_backend_legacy_postgres(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings(EVENT_STORE_BACKEND="postgres")
        with pytest.raises(ValueError, match="must be 'transactional_postgres'.*got 'postgres'"):
            get_transactional_event_store(pool=_fake_pool(), settings=s)

    def test_fails_when_backend_redis_streams(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings(EVENT_STORE_BACKEND="redis_streams")
        with pytest.raises(ValueError, match="must be 'transactional_postgres'.*got 'redis_streams'"):
            get_transactional_event_store(pool=_fake_pool(), settings=s)

    def test_fails_when_dsn_missing(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings()
        # Override DSN to None by setting it in env then removing
        import os
        os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)
        # Rebuild settings without DSN
        for k, v in _VALID_ENV.items():
            os.environ[k] = v
        os.environ.pop("EVENT_STORE_POSTGRES_DSN", None)
        try:
            s_no_dsn = Settings()
        finally:
            for k in _VALID_ENV:
                os.environ.pop(k, None)
        with pytest.raises(ValueError, match="EVENT_STORE_POSTGRES_DSN is required"):
            get_transactional_event_store(pool=_fake_pool(), settings=s_no_dsn)

    def test_fails_when_dsn_empty_string(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings(EVENT_STORE_POSTGRES_DSN="")
        with pytest.raises(ValueError, match="EVENT_STORE_POSTGRES_DSN is required"):
            get_transactional_event_store(pool=_fake_pool(), settings=s)

    def test_fails_when_pool_is_none(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings()
        with pytest.raises(ValueError, match="pool is required"):
            get_transactional_event_store(pool=None, settings=s)


class TestGetTransactionalEventStoreSafety:
    """T8: safety — no pool creation, no connection, no DSN in errors."""

    def test_does_not_create_pool(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings()
        pool = _fake_pool()
        store = get_transactional_event_store(pool=pool, settings=s)
        # Store should exist, pool should not have been used to acquire connections
        assert isinstance(store, TransactionalPostgresEventStore)
        pool.acquire.assert_not_called()

    def test_does_not_call_pool_acquire(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        s = _make_settings()
        pool = _fake_pool()
        get_transactional_event_store(pool=pool, settings=s)
        pool.acquire.assert_not_called()

    def test_dsn_not_in_error_messages(self) -> None:
        from app.infrastructure.event_store.factory import get_transactional_event_store
        # Test with missing DSN
        import os
        for k in _VALID_ENV:
            os.environ.pop(k, None)
        try:
            s_no_dsn = Settings()
        finally:
            pass
        with pytest.raises(ValueError) as exc_info:
            get_transactional_event_store(pool=_fake_pool(), settings=s_no_dsn)
        error_msg = str(exc_info.value)
        assert "postgresql://" not in error_msg
        assert "user:pwd" not in error_msg

    def test_uses_global_settings_when_none_provided(self) -> None:
        """When settings=None, the function should use the global settings
        (not raise TypeError for missing argument)."""
        from app.infrastructure.event_store.factory import get_transactional_event_store
        from app.core.config import settings as _global
        # If global settings has flag=False, we expect ValueError (not TypeError)
        # This proves the function read from global settings when settings=None.
        with pytest.raises(ValueError, match="EVENT_DRIVEN_ENABLED must be true"):
            get_transactional_event_store(pool=_fake_pool())


class TestMaskDsnHost:
    """T4/T8: DSN masking helper."""

    def test_masks_full_dsn(self) -> None:
        from app.infrastructure.event_store.factory import _mask_dsn_host
        assert _mask_dsn_host("postgresql://user:pwd@host.example.com:5432/db") == "host.example.com:5432"

    def test_masks_simple_dsn(self) -> None:
        from app.infrastructure.event_store.factory import _mask_dsn_host
        assert _mask_dsn_host("postgresql://u:p@localhost:5432/mydb") == "localhost:5432"

    def test_returns_unknown_on_bad_dsn(self) -> None:
        from app.infrastructure.event_store.factory import _mask_dsn_host
        assert _mask_dsn_host("not-a-dsn") == "unknown"

    def test_returns_unknown_on_empty(self) -> None:
        from app.infrastructure.event_store.factory import _mask_dsn_host
        assert _mask_dsn_host("") == "unknown"


# ---------------------------------------------------------------------------
# T9 — Tests for get_event_store() legacy compatibility
# ---------------------------------------------------------------------------


class TestLegacyGetEventStoreCompatibility:
    """T9: legacy factory is not broken by the new EDD factory."""

    def test_returns_inmemory_by_default(self) -> None:
        from app.infrastructure.event_store.factory import get_event_store
        from app.infrastructure.event_store.in_memory import InMemoryEventStore
        store = get_event_store()
        assert isinstance(store, InMemoryEventStore)

    def test_does_not_return_transactional_postgres_for_legacy_backend(self) -> None:
        """When EVENT_STORE_BACKEND=transactional_postgres, legacy factory
        does NOT know this backend and should fall through to default (memory)."""
        from app.infrastructure.event_store.factory import get_event_store
        from app.infrastructure.event_store.in_memory import InMemoryEventStore
        import os
        os.environ["EVENT_STORE_BACKEND"] = "transactional_postgres"
        try:
            store = get_event_store()
            # Legacy factory does not recognize transactional_postgres → falls to InMemory
            assert isinstance(store, InMemoryEventStore)
        finally:
            os.environ.pop("EVENT_STORE_BACKEND", None)


# ---------------------------------------------------------------------------
# T10 — Canaries: runtime activation guard
# ---------------------------------------------------------------------------


class TestNonActivationCanaries:
    """T10: self-check that new tests do not import prohibited runtime modules."""

    def test_new_test_file_does_not_import_main(self) -> None:
        """tests/unit/test_factory_event_store.py must not import app.main."""
        import ast
        path = __file__
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "app.main", f"prohibited import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("app.main"):
                    assert False, f"prohibited import from: {node.module}"

    def test_new_test_file_does_not_import_conversation_saga(self) -> None:
        """tests/unit/test_factory_event_store.py must not import ConversationSaga."""
        import ast
        path = __file__
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "conversation_saga" not in alias.name.lower(), f"prohibited import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module and "conversation_saga" in node.module.lower():
                    assert False, f"prohibited import from: {node.module}"

    def test_new_test_file_does_not_import_event_publisher_impl(self) -> None:
        """tests/unit/test_factory_event_store.py must not import EventPublisherImpl."""
        import ast
        path = __file__
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "EventPublisherImpl", f"prohibited import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names = [a.name for a in node.names]
                    assert "EventPublisherImpl" not in names, f"prohibited: EventPublisherImpl from {node.module}"


# ---------------------------------------------------------------------------
# T7 — /chat not-activation canaries (EDD Prompt 8)
# ---------------------------------------------------------------------------


class TestChatNotActivationCanaries:
    """Canaries that ensure /chat and process_message remain untouched.

    All checks are static-source-based: no import of app.main, no runtime,
    no TestClient.  These canaries are part of T7 and run as part of the
    unit suite, not in the integration suite.
    """

    @staticmethod
    def _read(relpath: str) -> str:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        return (repo_root / relpath).read_text(encoding="utf-8")

    def test_orchestrator_still_uses_inmemory_event_store(self) -> None:
        """K1: process_message continues to use InMemoryEventStore()."""
        text = self._read("app/agent/orchestrator.py")
        assert "InMemoryEventStore(" in text, (
            "K1: app/agent/orchestrator.py must still instantiate InMemoryEventStore"
        )

    def test_orchestrator_does_not_use_get_event_store(self) -> None:
        """K2: process_message must not call get_event_store."""
        text = self._read("app/agent/orchestrator.py")
        assert "get_event_store" not in text, (
            "K2: app/agent/orchestrator.py must not use get_event_store"
        )

    def test_orchestrator_does_not_reference_app_state(self) -> None:
        """K3: process_message must not read app.state."""
        text = self._read("app/agent/orchestrator.py")
        assert "app.state" not in text, (
            "K3: app/agent/orchestrator.py must not reference app.state"
        )

    def test_orchestrator_does_not_reference_postgres_pool(self) -> None:
        """K4: process_message must not reference postgres_pool."""
        text = self._read("app/agent/orchestrator.py")
        assert "postgres_pool" not in text, (
            "K4: app/agent/orchestrator.py must not reference postgres_pool"
        )

    def test_main_does_not_pass_postgres_pool_to_request(self) -> None:
        """K5: app/main.py must not access request.app.state.postgres_pool."""
        text = self._read("app/main.py")
        assert "request.app.state.postgres_pool" not in text, (
            "K5: app/main.py must not access request.app.state.postgres_pool"
        )

    def test_main_does_not_import_asyncpg(self) -> None:
        """K6: app/main.py must not import asyncpg."""
        text = self._read("app/main.py")
        assert "import asyncpg" not in text, (
            "K6: app/main.py must not import asyncpg"
        )

    def test_main_registers_lifespan(self) -> None:
        """K7: app/main.py must register lifespan=event_driven_lifespan."""
        text = self._read("app/main.py")
        assert "lifespan=" in text, (
            "K7: app/main.py must register a lifespan"
        )
        assert "event_driven_lifespan" in text, (
            "K7: app/main.py must reference event_driven_lifespan"
        )

    def test_main_chat_handler_still_calls_process_message(self) -> None:
        """K8: /chat handler in app/main.py must still call process_message."""
        text = self._read("app/main.py")
        assert "process_message(payload)" in text, (
            "K8: app/main.py /chat handler must call process_message(payload)"
        )
