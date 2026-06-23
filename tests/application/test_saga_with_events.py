"""Tests for ConversationSaga with EventPublisher."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.application.sagas.conversation_saga import ConversationContext, ConversationSaga
from app.application.sagas.event_publisher import EventPublisherImpl, NullEventPublisher
from app.domain.events import (
    AgentRunCompleted,
    AgentRunStarted,
    AgentRouteSelected,
    ConversationMemoryLoaded,
    ConversationMemorySaved,
    MessageProcessingFailed,
    OcrExtractionCompleted,
    RagContextRetrieved,
)
from app.infrastructure.event_store.in_memory import InMemoryEventStore


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
class _FakeRagResult:
    context: str = "RAG CTX"
    chunks_used: list = None
    def __post_init__(self):
        if self.chunks_used is None:
            self.chunks_used = []


@dataclass
class _FakeAgentResult:
    output: str = "Resposta"
    error: str | None = None
    messages: list = None
    tool_name: str = "pi_agent"
    def __post_init__(self):
        if self.messages is None:
            self.messages = []


def _make_saga(**kwargs) -> tuple[ConversationSaga, InMemoryEventStore]:
    store = InMemoryEventStore()
    publisher = EventPublisherImpl(store)
    defaults = dict(
        load_memory_fn=AsyncMock(return_value=_FakeMemoryResult()),
        ocr_fn=AsyncMock(return_value=type("R", (), {"extractions": []})()),
        route_fn=AsyncMock(return_value=_FakeRouteResult()),
        rag_fn=AsyncMock(return_value=_FakeRagResult()),
        run_agent_fn=AsyncMock(return_value=_FakeAgentResult()),
        save_memory_fn=AsyncMock(),
        event_publisher=publisher,
    )
    defaults.update(kwargs)
    saga = ConversationSaga(**defaults)
    return saga, store


# =========================================================================
# Event publishing from saga steps
# =========================================================================
class TestSagaEvents:
    @pytest.mark.asyncio
    async def test_load_memory_publishes_event(self) -> None:
        saga, store = _make_saga()
        ctx = ConversationContext(conversation_id="c1", message_original="hello")
        await saga._step_load_memory(ctx)
        events = await store.read("conversation:c1")
        assert any(type(e).__name__ == "ConversationMemoryLoaded" for e in events)

    @pytest.mark.asyncio
    async def test_route_publishes_event(self) -> None:
        saga, store = _make_saga()
        ctx = ConversationContext(message_original="hello")
        await saga._step_route(ctx)
        events = await store.read("conversation:anonymous")
        assert any(type(e).__name__ == "AgentRouteSelected" for e in events)

    @pytest.mark.asyncio
    async def test_retrieve_rag_publishes_event_for_pims(self) -> None:
        saga, store = _make_saga()
        ctx = ConversationContext(agent_route="pims", message_original="tag X")
        await saga._step_retrieve_rag(ctx)
        events = await store.read("conversation:anonymous")
        assert any(type(e).__name__ == "RagContextRetrieved" for e in events)

    @pytest.mark.asyncio
    async def test_retrieve_rag_no_event_for_general(self) -> None:
        saga, store = _make_saga(route_fn=AsyncMock(return_value=_FakeRouteResult(_route="conversa_comum")))
        ctx = ConversationContext(agent_route="conversa_comum")
        await saga._step_retrieve_rag(ctx)
        events = await store.read("conversation:anonymous")
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_run_agent_publishes_start_and_complete(self) -> None:
        saga, store = _make_saga()
        ctx = ConversationContext(
            agent_route="pims", message_original="hello",
            user_id="u1", conversation_id="c1",
        )
        await saga._step_run_agent(ctx)
        events = await store.read("conversation:c1")
        types = [type(e).__name__ for e in events]
        assert "AgentRunStarted" in types
        assert "AgentRunCompleted" in types

    @pytest.mark.asyncio
    async def test_save_memory_publishes_event(self) -> None:
        saga, store = _make_saga()
        ctx = ConversationContext(
            conversation_id="c1", message_original="hi",
            agent_output="bye", agent_route="pims",
            user_id="u1", tool_name="pi_agent",
        )
        await saga._step_save_memory(ctx)
        events = await store.read("conversation:c1")
        assert any(type(e).__name__ == "ConversationMemorySaved" for e in events)

    @pytest.mark.asyncio
    async def test_error_publishes_message_processing_failed(self) -> None:
        async def _fail(cmd):
            raise RuntimeError("boom")

        saga, store = _make_saga(route_fn=_fail)
        ctx = ConversationContext(message_original="hello")
        result = await saga.execute(ctx)
        assert result.error is not None
        events = await store.read("conversation:anonymous")
        types = [type(e).__name__ for e in events]
        assert "MessageProcessingFailed" in types

    @pytest.mark.asyncio
    async def test_full_pims_flow_publishes_multiple_events(self) -> None:
        saga, store = _make_saga()
        ctx = ConversationContext(
            user_id="u1", conversation_id="c1",
            message_original="tag X",
        )
        await saga.execute(ctx)
        events = await store.read("conversation:c1")
        types = [type(e).__name__ for e in events]
        assert "ConversationMemoryLoaded" in types
        assert "AgentRouteSelected" in types
        assert "RagContextRetrieved" in types
        assert "AgentRunStarted" in types
        assert "AgentRunCompleted" in types
        assert "ConversationMemorySaved" in types
        assert len(events) >= 6


# =========================================================================
# NullEventPublisher with saga
# =========================================================================
class TestSagaWithNullPublisher:
    @pytest.mark.asyncio
    async def test_saga_works_with_null_publisher(self) -> None:
        store = InMemoryEventStore()
        null_pub = NullEventPublisher()
        saga = ConversationSaga(
            load_memory_fn=AsyncMock(return_value=_FakeMemoryResult()),
            ocr_fn=AsyncMock(return_value=type("R", (), {"extractions": []})()),
        route_fn=AsyncMock(return_value=_FakeRouteResult()),
            rag_fn=AsyncMock(return_value=_FakeRagResult()),
            run_agent_fn=AsyncMock(return_value=_FakeAgentResult()),
            save_memory_fn=AsyncMock(),
            event_publisher=null_pub,
        )
        ctx = ConversationContext(user_id="u1", conversation_id="c1", message_original="hi")
        result = await saga.execute(ctx)
        assert result.error is None
        # No events published
        events = await store.read("conversation:c1")
        assert len(events) == 0
