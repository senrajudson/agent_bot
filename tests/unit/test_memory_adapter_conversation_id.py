"""Unit tests for ConversationId adoption in memory adapter (Prompt 3 Ciclo 2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.value_objects import ConversationId


class TestMemoryKey:
    """_memory_key should accept ConversationId and produce the same Redis key."""

    def test_memory_key_with_conversation_id(self):
        from app.services.chat_memory_service import _memory_key

        assert _memory_key(ConversationId("alice")) == "pi_chat:memory:alice:turns"

    def test_memory_key_with_anonymous(self):
        from app.services.chat_memory_service import _memory_key

        assert _memory_key(ConversationId("anonymous")) == "pi_chat:memory:anonymous:turns"

    def test_memory_key_preserves_special_chars(self):
        from app.services.chat_memory_service import _memory_key

        assert _memory_key(ConversationId("users/u1")) == "pi_chat:memory:users/u1:turns"


class TestServiceInternalConversion:
    """Service must convert str -> ConversationId internally; same Redis key."""

    @pytest.mark.asyncio
    async def test_load_converts_str_to_conversation_id(self, monkeypatch):
        from app.services.chat_memory_service import load_memory_turns

        captured: dict = {}

        async def fake_lrange(key, start, end):
            captured["key"] = key
            return []

        mock_client = MagicMock()
        mock_client.lrange = fake_lrange
        monkeypatch.setattr(
            "app.services.chat_memory_service.get_redis_client",
            lambda: mock_client,
        )

        await load_memory_turns("conv-1")

        assert captured["key"] == "pi_chat:memory:conv-1:turns"

    @pytest.mark.asyncio
    async def test_load_with_none_returns_empty(self):
        from app.services.chat_memory_service import load_memory_turns

        result = await load_memory_turns(None)
        assert result == []

    @pytest.mark.asyncio
    async def test_append_converts_str_to_conversation_id(self, monkeypatch):
        from app.services.chat_memory_service import append_memory_turns

        captured: dict = {}

        def fake_rpush(key, *args):
            captured["key"] = key

        mock_pipe = MagicMock()
        mock_pipe.rpush = fake_rpush
        mock_pipe.ltrim = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[None, None, None])
        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        monkeypatch.setattr(
            "app.services.chat_memory_service.get_redis_client",
            lambda: mock_client,
        )

        await append_memory_turns(
            "conv-1", user_message="hi", assistant_message="hello", metadata={}
        )

        assert captured["key"] == "pi_chat:memory:conv-1:turns"

    @pytest.mark.asyncio
    async def test_append_with_none_is_noop(self, monkeypatch):
        from app.services.chat_memory_service import append_memory_turns

        mock_client = MagicMock()
        monkeypatch.setattr(
            "app.services.chat_memory_service.get_redis_client",
            lambda: mock_client,
        )

        await append_memory_turns(None, user_message="hi", assistant_message="hello")

        mock_client.pipeline.assert_not_called()


class TestMemoryAdapterConversion:
    """_MemoryAdapter converts ConversationId to str at boundary."""

    @pytest.mark.asyncio
    async def test_adapter_load_turns_with_conversation_id_calls_str(self):
        from app.agent.orchestrator import _MemoryAdapter

        adapter = _MemoryAdapter()
        cid = ConversationId("alice")

        with patch(
            "app.agent.orchestrator.load_memory_turns",
            new=AsyncMock(return_value=[]),
        ) as mock_load:
            await adapter.load_turns(cid)

        mock_load.assert_awaited_once_with("alice", None)

    @pytest.mark.asyncio
    async def test_adapter_append_turns_with_conversation_id_calls_str(self):
        from app.agent.orchestrator import _MemoryAdapter

        adapter = _MemoryAdapter()
        cid = ConversationId("alice")

        with patch(
            "app.agent.orchestrator.append_memory_turns",
            new=AsyncMock(),
        ) as mock_append:
            await adapter.append_turns(
                cid, user_message="hi", assistant_message="hello", metadata={}
            )

        mock_append.assert_awaited_once_with("alice", "hi", "hello", {})

    @pytest.mark.asyncio
    async def test_adapter_load_turns_with_str_passthrough(self):
        from app.agent.orchestrator import _MemoryAdapter

        adapter = _MemoryAdapter()

        with patch(
            "app.agent.orchestrator.load_memory_turns",
            new=AsyncMock(return_value=[]),
        ) as mock_load:
            await adapter.load_turns("raw-str")

        mock_load.assert_awaited_once_with("raw-str", None)

    @pytest.mark.asyncio
    async def test_adapter_load_turns_with_none_passthrough(self):
        from app.agent.orchestrator import _MemoryAdapter

        adapter = _MemoryAdapter()

        with patch(
            "app.agent.orchestrator.load_memory_turns",
            new=AsyncMock(return_value=[]),
        ) as mock_load:
            result = await adapter.load_turns(None)

        mock_load.assert_awaited_once_with(None, None)
        assert result == []

    @pytest.mark.asyncio
    async def test_adapter_append_turns_with_none_passthrough(self):
        from app.agent.orchestrator import _MemoryAdapter

        adapter = _MemoryAdapter()

        with patch(
            "app.agent.orchestrator.append_memory_turns",
            new=AsyncMock(),
        ) as mock_append:
            await adapter.append_turns(None, user_message="hi", assistant_message="hello")

        mock_append.assert_awaited_once_with(None, "hi", "hello", None)


class TestAdapterAcceptsConversationId:
    """Adapter signature accepts ConversationId (duck-typed)."""

    def test_adapter_signature_unchanged(self):
        """The signature of adapter methods must remain (conversation_id, ...)."""
        import inspect

        from app.agent.orchestrator import _MemoryAdapter

        load_sig = inspect.signature(_MemoryAdapter.load_turns)
        append_sig = inspect.signature(_MemoryAdapter.append_turns)

        assert "conversation_id" in load_sig.parameters
        assert "conversation_id" in append_sig.parameters
        assert "max_turns" in load_sig.parameters
        assert "user_message" in append_sig.parameters
        assert "assistant_message" in append_sig.parameters
        assert "metadata" in append_sig.parameters
