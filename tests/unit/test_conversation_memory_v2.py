"""Tests for RedisConversationMemory (v2, EventStore-backed)."""
from __future__ import annotations

import pytest

from app.infrastructure.conversation.redis_memory_v2 import RedisConversationMemory
from app.infrastructure.event_store.in_memory import InMemoryEventStore
from app.domain.projections import ConversationTurn


# =========================================================================
# RedisConversationMemory with InMemoryEventStore
# =========================================================================
class TestRedisConversationMemory:
    @pytest.fixture
    def memory(self) -> RedisConversationMemory:
        return RedisConversationMemory(event_store=InMemoryEventStore())

    @pytest.mark.asyncio
    async def test_load_empty_stream(self, memory: RedisConversationMemory) -> None:
        turns = await memory.load_turns("nonexistent")
        assert turns == []

    @pytest.mark.asyncio
    async def test_load_none_conversation_id(self, memory: RedisConversationMemory) -> None:
        turns = await memory.load_turns(None)
        assert turns == []

    @pytest.mark.asyncio
    async def test_append_creates_two_events(self, memory: RedisConversationMemory) -> None:
        await memory.append_turns("c1", "user msg", "assistant msg")
        turns = await memory.load_turns("c1")
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content == "user msg"
        assert turns[1].role == "assistant"
        assert turns[1].content == "assistant msg"

    @pytest.mark.asyncio
    async def test_multiple_appends_replay_correctly(self, memory: RedisConversationMemory) -> None:
        await memory.append_turns("c1", "m1", "r1")
        await memory.append_turns("c1", "m2", "r2")
        await memory.append_turns("c1", "m3", "r3")
        turns = await memory.load_turns("c1")
        assert len(turns) == 6
        assert turns[0].content == "m1"
        assert turns[1].content == "r1"
        assert turns[4].content == "m3"
        assert turns[5].content == "r3"

    @pytest.mark.asyncio
    async def test_max_turns_limits_output(self, memory: RedisConversationMemory) -> None:
        await memory.append_turns("c1", "m1", "r1")
        await memory.append_turns("c1", "m2", "r2")
        await memory.append_turns("c1", "m3", "r3")
        turns = await memory.load_turns("c1", max_turns=4)
        assert len(turns) == 4
        # Should keep last 4: m2, r2, m3, r3
        assert turns[0].content == "m2"
        assert turns[3].content == "r3"

    @pytest.mark.asyncio
    async def test_metadata_preserved(self, memory: RedisConversationMemory) -> None:
        await memory.append_turns("c1", "hi", "hello", metadata={"tool": "pi_agent"})
        turns = await memory.load_turns("c1")
        assert turns[0].metadata == {"tool": "pi_agent"}
        assert turns[1].metadata == {"tool": "pi_agent"}

    def test_format_for_prompt(self, memory: RedisConversationMemory) -> None:
        turns = [
            ConversationTurn(role="user", content="question", created_at="t1"),
            ConversationTurn(role="assistant", content="answer", created_at="t2"),
        ]
        result = memory.format_for_prompt(turns)
        assert "> Usuário: question" in result
        assert "> Assistente: answer" in result
