"""Tests for SaveConversationTurnMemorySaver adapter."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.outbox.handlers.conversation_memory_save_handler import (
    SaveConversationTurnMemorySaver,
)


@pytest.fixture
def fake_handler() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def adapter(fake_handler: AsyncMock) -> SaveConversationTurnMemorySaver:
    return SaveConversationTurnMemorySaver(save_handler=fake_handler)


class TestSaveConversationTurnMemorySaver:
    async def test_save_calls_handler_with_full_payload(
        self, adapter: SaveConversationTurnMemorySaver, fake_handler: AsyncMock
    ) -> None:
        payload = {
            "conversation_id": "user-123",
            "user_message": "Hello",
            "assistant_message": "Hi!",
            "metadata": {"categoria": "pims"},
        }
        await adapter.save(payload)
        fake_handler.handle.assert_awaited_once()
        command = fake_handler.handle.call_args[0][0]
        assert command.conversation_id == "user-123"
        assert command.user_message == "Hello"
        assert command.assistant_message == "Hi!"
        assert command.metadata == {"categoria": "pims"}

    async def test_save_with_missing_user_id(
        self, adapter: SaveConversationTurnMemorySaver, fake_handler: AsyncMock
    ) -> None:
        payload = {
            "conversation_id": "user-123",
            "user_message": "Hello",
            "assistant_message": "Hi!",
        }
        await adapter.save(payload)
        command = fake_handler.handle.call_args[0][0]
        assert command.conversation_id == "user-123"

    async def test_save_with_empty_metadata(
        self, adapter: SaveConversationTurnMemorySaver, fake_handler: AsyncMock
    ) -> None:
        payload = {
            "conversation_id": "user-123",
            "user_message": "Hello",
            "assistant_message": "Hi!",
        }
        await adapter.save(payload)
        command = fake_handler.handle.call_args[0][0]
        assert command.metadata == {}

    async def test_save_propagates_handler_exception(
        self, adapter: SaveConversationTurnMemorySaver, fake_handler: AsyncMock
    ) -> None:
        fake_handler.handle.side_effect = RuntimeError("Redis down")
        payload = {
            "conversation_id": "user-123",
            "user_message": "Hello",
            "assistant_message": "Hi!",
        }
        with pytest.raises(RuntimeError, match="Redis down"):
            await adapter.save(payload)

    async def test_save_raises_on_empty_payload(
        self, adapter: SaveConversationTurnMemorySaver
    ) -> None:
        with pytest.raises(ValueError, match="payload is empty"):
            await adapter.save({})

    async def test_save_raises_on_missing_conversation_id(
        self, adapter: SaveConversationTurnMemorySaver
    ) -> None:
        payload = {"user_message": "Hello", "assistant_message": "Hi!"}
        with pytest.raises(ValueError, match="conversation_id is required"):
            await adapter.save(payload)

    async def test_save_raises_on_blank_conversation_id(
        self, adapter: SaveConversationTurnMemorySaver
    ) -> None:
        payload = {
            "conversation_id": "",
            "user_message": "Hello",
            "assistant_message": "Hi!",
        }
        with pytest.raises(ValueError, match="conversation_id is required"):
            await adapter.save(payload)
