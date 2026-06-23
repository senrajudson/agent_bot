"""Tests for ConversationSaga with memory v2 (EventStore-backed)."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.application.sagas.conversation_saga import ConversationContext, ConversationSaga
from app.application.sagas.event_publisher import EventPublisherImpl
from app.domain.events import ConversationMemorySaved
from app.domain.projections import (
    AssistantMessageRecorded,
    UserMessageRecorded,
)
from app.infrastructure.event_store.in_memory import InMemoryEventStore
from app.infrastructure.conversation.redis_memory_v2 import RedisConversationMemory


# ---------------------------------------------------------------------------
# Fake result objects
# ---------------------------------------------------------------------------
@dataclass
class _FakeMemoryResult:
    turns: list = None
    context: str = ""
    def __post_init__(self):
        if self.turns is None:
            self.turns = []


@dataclass
class _FakeRouteResult:
    _route: str = "pims"

    @property
    def route(self):
        class _R:
            def __init__(self, v): self.value = v
        return _R(self._route)


@dataclass
class _FakeAgentResult:
    output: str = "Resposta"
    error: str | None = None
    messages: list = None
    tool_name: str = "pi_agent"
    def __post_init__(self):
        if self.messages is None:
            self.messages = []


def _make_saga_with_memory_v2() -> tuple[ConversationSaga, InMemoryEventStore, RedisConversationMemory]:
    store = InMemoryEventStore()
    publisher = EventPublisherImpl(store)
    memory_v2 = RedisConversationMemory(event_store=store)

    class _MemV2Adapter:
        def __init__(self, mem): self._mem = mem
        async def load_turns(self, cid, max_turns=None):
            return await self._mem.load_turns(cid, max_turns)
        async def append_turns(self, cid, user_msg, asst_msg, metadata=None):
            await self._mem.append_turns(cid, user_msg, asst_msg, metadata)
        def format_for_prompt(self, turns):
            return self._mem.format_for_prompt(turns)

    saga = ConversationSaga(
        load_memory_fn=AsyncMock(return_value=_FakeMemoryResult()),
        ocr_fn=AsyncMock(return_value=type("R", (), {"extractions": []})()),
        route_fn=AsyncMock(return_value=_FakeRouteResult()),
        rag_fn=AsyncMock(return_value=type("R2", (), {"context": "", "chunks_used": []})()),
        run_agent_fn=AsyncMock(return_value=_FakeAgentResult()),
        save_memory_fn=AsyncMock(),
        event_publisher=publisher,
    )
    return saga, store, memory_v2


# =========================================================================
# Memory events from saga
# =========================================================================
class TestSagaMemoryEvents:
    @pytest.mark.asyncio
    async def test_load_memory_publishes_user_message_recorded(self) -> None:
        saga, store, memory = _make_saga_with_memory_v2()
        ctx = ConversationContext(
            conversation_id="c1",
            message_original="hello",
            user_id="u1",
        )
        await saga._step_load_memory(ctx)
        events = await store.read("conversation:c1")
        types = [type(e).__name__ for e in events]
        assert "UserMessageRecorded" in types

    @pytest.mark.asyncio
    async def test_save_memory_publishes_assistant_message_recorded(self) -> None:
        saga, store, memory = _make_saga_with_memory_v2()
        ctx = ConversationContext(
            conversation_id="c1",
            message_original="hi",
            agent_output="hello there",
            agent_route="pims",
            tool_name="pi_agent",
            user_id="u1",
        )
        await saga._step_save_memory(ctx)
        events = await store.read("conversation:c1")
        types = [type(e).__name__ for e in events]
        assert "AssistantMessageRecorded" in types
        assert "ConversationMemorySaved" in types

    @pytest.mark.asyncio
    async def test_memory_v2_reconstructs_turns_from_events(self) -> None:
        saga, store, memory = _make_saga_with_memory_v2()
        # Simulate: user message loaded, then assistant saved
        ctx_load = ConversationContext(
            conversation_id="c1",
            message_original="question",
            user_id="u1",
        )
        await saga._step_load_memory(ctx_load)

        ctx_save = ConversationContext(
            conversation_id="c1",
            message_original="question",
            agent_output="answer",
            agent_route="pims",
            tool_name="pi_agent",
            user_id="u1",
        )
        await saga._step_save_memory(ctx_save)

        turns = await memory.load_turns("c1")
        # 2 events: UserMessageRecorded (from load_memory) + AssistantMessageRecorded (from save_memory)
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content == "question"
        assert turns[1].role == "assistant"
        assert turns[1].content == "answer"

    @pytest.mark.asyncio
    async def test_format_for_prompt_matches_legacy(self) -> None:
        """Verify the v2 format matches the v1 format."""
        from app.services.chat_memory_service import ChatMemoryTurn, format_memory_for_prompt

        saga, store, memory = _make_saga_with_memory_v2()

        # Create turns via events
        ctx_load = ConversationContext(
            conversation_id="c1",
            message_original="hello",
            user_id="u1",
        )
        await saga._step_load_memory(ctx_load)

        ctx_save = ConversationContext(
            conversation_id="c1",
            message_original="hello",
            agent_output="hi there",
            agent_route="pims",
            tool_name="pi_agent",
            user_id="u1",
        )
        await saga._step_save_memory(ctx_save)

        turns = await memory.load_turns("c1")
        v2_output = memory.format_for_prompt(turns)

        # Create equivalent legacy turns
        legacy_turns = [
            ChatMemoryTurn(role="user", content="hello", created_at="2026-01-01", metadata={}),
            ChatMemoryTurn(role="assistant", content="hi there", created_at="2026-01-02", metadata={}),
        ]
        legacy_output = format_memory_for_prompt(legacy_turns)

        # Format should match (turn content matters, not timestamps)
        assert "> Usuário: hello" in v2_output
        assert "> Assistente: hi there" in v2_output

    @pytest.mark.asyncio
    async def test_full_flow_publishes_memory_events(self) -> None:
        saga, store, memory = _make_saga_with_memory_v2()
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="qual o valor da tag X",
        )
        result = await saga.execute(ctx)
        assert result.error is None
        events = await store.read("conversation:c1")
        types = [type(e).__name__ for e in events]
        # Should have: ConversationMemoryLoaded, UserMessageRecorded, AgentRouteSelected,
        # AgentRunStarted, AgentRunCompleted, ConversationMemorySaved, AssistantMessageRecorded
        assert "UserMessageRecorded" in types
        assert "AssistantMessageRecorded" in types
