"""Characterization tests for memory service (TASK-007).

Locks down memory behavior:
- load_memory_turns with turns → list of ChatMemoryTurn
- load_memory_turns with conversation_id=None → empty list
- append_memory_turns with metadata → pipeline called
- append_memory_turns with conversation_id=None → no-op
- format_memory_for_prompt with turns → observable structure
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestLoadMemoryTurns:
    """M-1 and M-2: load_memory_turns behavior."""

    @pytest.mark.asyncio
    async def test_load_with_turns(self, monkeypatch):
        from app.services.chat_memory_service import ChatMemoryTurn

        turn = ChatMemoryTurn(
            role="user",
            content="hi",
            created_at="2026-01-01T10:00:00-03:00",
            metadata={},
        )

        mock_client = MagicMock()
        mock_client.lrange = AsyncMock(return_value=[turn.model_dump_json()])

        monkeypatch.setattr(
            "app.services.chat_memory_service.get_redis_client",
            lambda: mock_client,
        )

        from app.services.chat_memory_service import load_memory_turns

        result = await load_memory_turns("conv-1")

        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "hi"

    @pytest.mark.asyncio
    async def test_load_with_none_conversation_id(self):
        from app.services.chat_memory_service import load_memory_turns

        result = await load_memory_turns(None)

        assert result == []


class TestAppendMemoryTurns:
    """M-3 and M-4: append_memory_turns behavior."""

    @pytest.mark.asyncio
    async def test_append_with_metadata(self, monkeypatch):
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.rpush = MagicMock()
        mock_pipe.ltrim = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[None, None, None])
        mock_client.pipeline.return_value = mock_pipe

        monkeypatch.setattr(
            "app.services.chat_memory_service.get_redis_client",
            lambda: mock_client,
        )

        from app.services.chat_memory_service import append_memory_turns

        await append_memory_turns(
            "conv-1",
            user_message="hi",
            assistant_message="hello",
            metadata={"user_id": "u1"},
        )

        mock_pipe.rpush.assert_called_once()
        mock_pipe.ltrim.assert_called_once()
        mock_pipe.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_append_with_none_conversation_id(self, monkeypatch):
        mock_client = MagicMock()
        monkeypatch.setattr(
            "app.services.chat_memory_service.get_redis_client",
            lambda: mock_client,
        )

        from app.services.chat_memory_service import append_memory_turns

        await append_memory_turns(None, user_message="hi", assistant_message="hello")

        mock_client.pipeline.assert_not_called()


class TestFormatMemoryForPrompt:
    """M-5: format_memory_for_prompt observable structure."""

    def test_format_with_two_turns(self):
        from app.services.chat_memory_service import ChatMemoryTurn, format_memory_for_prompt

        turns = [
            ChatMemoryTurn(role="user", content="hi", created_at="2026-01-01T10:00:00-03:00", metadata={}),
            ChatMemoryTurn(role="assistant", content="hello", created_at="2026-01-01T10:00:01-03:00", metadata={}),
        ]

        result = format_memory_for_prompt(turns)

        assert "Usuário" in result
        assert "Assistente" in result
        assert "hi" in result
        assert "hello" in result
        # Verify order: user first, then assistant
        user_pos = result.index("Usuário")
        assistant_pos = result.index("Assistente")
        assert user_pos < assistant_pos

    def test_format_empty_turns(self):
        from app.services.chat_memory_service import format_memory_for_prompt

        result = format_memory_for_prompt([])
        assert result == ""
