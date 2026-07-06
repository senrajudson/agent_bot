"""Tests for ConversationSaga and ConversationContext."""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.sagas.conversation_saga import (
    ConversationContext,
    ConversationSaga,
    build_agent_user_message,
    build_rag_query,
    build_router_message,
)


# ---------------------------------------------------------------------------
# Fake result objects (match protocol expected by saga)
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class _FakeMemoryResult:
    turns: list = field(default_factory=list)
    context: str = ""


@dataclass
class _FakeOcrResult:
    extractions: list = field(default_factory=list)


@dataclass
class _FakeAgentRoute:
    _value: str = "pims"

    @property
    def value(self) -> str:
        return self._value


@dataclass
class _FakeRouteResult:
    route: _FakeAgentRoute = field(default_factory=lambda: _FakeAgentRoute("pims"))


@dataclass
class _FakeRagResult:
    context: str = "RAG CONTEXT HERE"
    chunks_used: list = field(default_factory=list)


@dataclass
class _FakeAgentResult:
    output: str = "Resposta do agente"
    error: str | None = None
    messages: list = field(default_factory=list)
    tool_name: str = "agent"


# ---------------------------------------------------------------------------
# Mock callables
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_load_memory():
    return AsyncMock(
        return_value=_FakeMemoryResult(
            turns=[{"role": "user", "content": "hi"}],
            context="> user: hi",
        )
    )


@pytest.fixture
def mock_ocr():
    return AsyncMock(return_value=_FakeOcrResult(extractions=[]))


@pytest.fixture
def mock_route():
    return AsyncMock(return_value=_FakeRouteResult(route=_FakeAgentRoute("pims")))


@pytest.fixture
def mock_route_general():
    return AsyncMock(return_value=_FakeRouteResult(route=_FakeAgentRoute("conversa_comum")))


@pytest.fixture
def mock_rag():
    return AsyncMock(
        return_value=_FakeRagResult(context="RAG CONTEXT HERE")
    )


@pytest.fixture
def mock_run_agent():
    return AsyncMock(
        return_value=_FakeAgentResult(
            output="O valor e 1523.4 Nm3/h",
            messages=[],
            tool_name="agent",
        )
    )


@pytest.fixture
def mock_run_agent_general():
    return AsyncMock(
        return_value=_FakeAgentResult(
            output="Ola! Como posso ajudar?",
            messages=[],
            tool_name="general_agent",
        )
    )


@pytest.fixture
def mock_save_memory():
    return AsyncMock(return_value=None)


def _make_saga(**kwargs) -> ConversationSaga:
    defaults = dict(
        load_memory_fn=AsyncMock(return_value=_FakeMemoryResult()),
        ocr_fn=AsyncMock(return_value=_FakeOcrResult()),
        route_fn=AsyncMock(return_value=_FakeRouteResult(route="pims")),
        rag_fn=AsyncMock(return_value=_FakeRagResult(context="")),
        run_agent_fn=AsyncMock(return_value=_FakeAgentResult()),
        save_memory_fn=AsyncMock(),
    )
    defaults.update(kwargs)
    return ConversationSaga(**defaults)


# =========================================================================
# ConversationContext
# =========================================================================
class TestConversationContext:
    def test_creates_with_defaults(self) -> None:
        ctx = ConversationContext()
        assert ctx.user_id is None
        assert ctx.message_original == ""
        assert ctx.images == []
        assert ctx.skip_ocr is True
        assert ctx.agent_route is None
        assert ctx.knowledge_context == ""
        assert ctx.error is None

    def test_is_frozen(self) -> None:
        ctx = ConversationContext(message_original="hi")
        with pytest.raises(AttributeError):
            ctx.message_original = "bye"  # type: ignore[misc]

    def test_can_be_replaced(self) -> None:
        ctx = ConversationContext(user_id="u1")
        new_ctx = replace(ctx, user_id="u2")
        assert ctx.user_id == "u1"
        assert new_ctx.user_id == "u2"

    def test_holds_all_required_fields(self) -> None:
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="hello",
            agent_route="pims",
            knowledge_context="ctx",
            agent_output="out",
            error="err",
        )
        assert ctx.user_id == "u1"
        assert ctx.conversation_id == "c1"
        assert ctx.message_original == "hello"
        assert ctx.agent_route == "pims"
        assert ctx.knowledge_context == "ctx"
        assert ctx.agent_output == "out"
        assert ctx.error == "err"


# =========================================================================
# Saga steps
# =========================================================================
class TestSagaSteps:
    @pytest.mark.asyncio
    async def test_load_memory_step(
        self, mock_load_memory, mock_ocr, mock_route, mock_rag,
        mock_run_agent, mock_save_memory,
    ) -> None:
        saga = _make_saga(
            load_memory_fn=mock_load_memory,
            ocr_fn=mock_ocr,
            route_fn=mock_route,
            rag_fn=mock_rag,
            run_agent_fn=mock_run_agent,
            save_memory_fn=mock_save_memory,
        )
        ctx = ConversationContext(conversation_id="c1")
        ctx = await saga._step_load_memory(ctx)
        mock_load_memory.assert_awaited_once()
        assert ctx.memory_context == "> user: hi"

    @pytest.mark.asyncio
    async def test_load_memory_skipped_when_no_conversation_id(self, mock_load_memory) -> None:
        saga = _make_saga(load_memory_fn=mock_load_memory)
        ctx = ConversationContext(conversation_id=None)
        ctx = await saga._step_load_memory(ctx)
        mock_load_memory.assert_not_awaited()
        assert ctx.memory_turns == []

    @pytest.mark.asyncio
    async def test_extract_ocr_step_with_images(self, mock_ocr) -> None:
        fake_ext = MagicMock(image_index=0, text="tag X", tags=["TAG_X"])
        mock_ocr_fn = AsyncMock(return_value=_FakeOcrResult(extractions=[fake_ext]))
        saga = _make_saga(ocr_fn=mock_ocr_fn)
        ctx = ConversationContext(images=[object()])
        ctx = await saga._step_extract_ocr(ctx)
        assert ctx.skip_ocr is False
        assert ctx.ocr_text is not None
        assert "TAG_X" in ctx.tags_encontradas

    @pytest.mark.asyncio
    async def test_extract_ocr_step_without_images(self, mock_ocr) -> None:
        saga = _make_saga(ocr_fn=mock_ocr)
        ctx = ConversationContext(images=[])
        ctx = await saga._step_extract_ocr(ctx)
        assert ctx.skip_ocr is True
        assert ctx.ocr_text is None

    @pytest.mark.asyncio
    async def test_route_step(self, mock_route) -> None:
        saga = _make_saga(route_fn=mock_route)
        ctx = ConversationContext(message_original="tag X")
        ctx = await saga._step_route(ctx)
        assert ctx.agent_route == "pims"

    @pytest.mark.asyncio
    async def test_retrieve_rag_step_for_pims(self, mock_rag) -> None:
        saga = _make_saga(rag_fn=mock_rag)
        ctx = ConversationContext(agent_route="pims", message_original="tag X")
        ctx = await saga._step_retrieve_rag(ctx)
        mock_rag.assert_awaited_once()
        assert ctx.knowledge_context == "RAG CONTEXT HERE"

    @pytest.mark.asyncio
    async def test_retrieve_rag_skipped_for_general(self, mock_rag) -> None:
        saga = _make_saga(rag_fn=mock_rag)
        ctx = ConversationContext(agent_route="conversa_comum")
        ctx = await saga._step_retrieve_rag(ctx)
        mock_rag.assert_not_awaited()
        assert ctx.knowledge_context == ""

    @pytest.mark.asyncio
    async def test_run_agent_step_pims(self, mock_run_agent) -> None:
        saga = _make_saga(run_agent_fn=mock_run_agent)
        ctx = ConversationContext(
            agent_route="pims", message_original="tag X",
            user_id="u1", conversation_id="c1",
        )
        ctx = await saga._step_run_agent(ctx)
        assert ctx.agent_output == "O valor e 1523.4 Nm3/h"
        assert ctx.tool_name == "agent"

    @pytest.mark.asyncio
    async def test_run_agent_step_general(self, mock_run_agent_general) -> None:
        saga = _make_saga(run_agent_fn=mock_run_agent_general)
        ctx = ConversationContext(
            agent_route="conversa_comum", message_original="ola",
            user_id="u1", conversation_id="c1",
        )
        ctx = await saga._step_run_agent(ctx)
        assert ctx.agent_output == "Ola! Como posso ajudar?"
        assert ctx.tool_name == "general_agent"

    @pytest.mark.asyncio
    async def test_save_memory_step(self, mock_save_memory) -> None:
        saga = _make_saga(save_memory_fn=mock_save_memory)
        ctx = ConversationContext(
            conversation_id="c1", message_original="hi",
            agent_output="bye", agent_route="pims",
            user_id="u1", tool_name="agent",
        )
        ctx = await saga._step_save_memory(ctx)
        mock_save_memory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_memory_skipped_when_empty(self, mock_save_memory) -> None:
        saga = _make_saga(save_memory_fn=mock_save_memory)
        ctx = ConversationContext(conversation_id="c1", message_original="", agent_output=None)
        ctx = await saga._step_save_memory(ctx)
        mock_save_memory.assert_not_awaited()


# =========================================================================
# Saga error handling
# =========================================================================
class TestSagaErrorHandling:
    @pytest.mark.asyncio
    async def test_error_in_first_step_halts_saga(self) -> None:
        async def _fail(cmd):
            raise RuntimeError("boom")

        saga = _make_saga(load_memory_fn=_fail)
        ctx = ConversationContext(conversation_id="c1")
        ctx = await saga.execute(ctx)
        assert ctx.error is not None
        assert "boom" in ctx.error

    @pytest.mark.asyncio
    async def test_error_in_middle_step_halts_saga(self) -> None:
        async def _fail(cmd):
            raise ValueError("nope")

        saga = _make_saga(route_fn=_fail)
        ctx = ConversationContext(message_original="hello")
        ctx = await saga.execute(ctx)
        assert ctx.error is not None
        assert "nope" in ctx.error

    @pytest.mark.asyncio
    async def test_error_records_error_message(self) -> None:
        async def _fail(cmd):
            raise RuntimeError("test error")

        saga = _make_saga(run_agent_fn=_fail)
        ctx = ConversationContext(
            agent_route="pims", message_original="x",
            user_id="u1", conversation_id="c1",
        )
        ctx = await saga.execute(ctx)
        assert ctx.agent_output is not None
        assert "Não consegui executar" in ctx.agent_output
        assert ctx.tool_name == "orchestrator"


# =========================================================================
# Full flow
# =========================================================================
class TestSagaFullFlow:
    @pytest.mark.asyncio
    async def test_full_pims_flow(
        self, mock_load_memory, mock_ocr, mock_route, mock_rag,
        mock_run_agent, mock_save_memory,
    ) -> None:
        saga = ConversationSaga(
            load_memory_fn=mock_load_memory,
            ocr_fn=mock_ocr,
            route_fn=mock_route,
            rag_fn=mock_rag,
            run_agent_fn=mock_run_agent,
            save_memory_fn=mock_save_memory,
        )
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="qual o valor da LFI_RB3_VAZ_GN_TOTAL",
        )
        result = await saga.execute(ctx)
        assert result.error is None
        assert result.agent_route == "pims"
        assert result.agent_output == "O valor e 1523.4 Nm3/h"
        assert result.knowledge_context == "RAG CONTEXT HERE"
        mock_load_memory.assert_awaited_once()
        mock_route.assert_awaited_once()
        mock_rag.assert_awaited_once()
        mock_run_agent.assert_awaited_once()
        mock_save_memory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_general_flow(
        self, mock_load_memory, mock_ocr, mock_route_general,
        mock_run_agent_general, mock_save_memory,
    ) -> None:
        saga = ConversationSaga(
            load_memory_fn=mock_load_memory,
            ocr_fn=mock_ocr,
            route_fn=mock_route_general,
            rag_fn=AsyncMock(),
            run_agent_fn=mock_run_agent_general,
            save_memory_fn=mock_save_memory,
        )
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="ola",
        )
        result = await saga.execute(ctx)
        assert result.error is None
        assert result.agent_route == "conversa_comum"
        assert result.agent_output == "Ola! Como posso ajudar?"
        mock_save_memory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_flow_with_error(self) -> None:
        async def _fail(cmd):
            raise RuntimeError("LLM offline")

        saga = _make_saga(route_fn=_fail)
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="test",
        )
        result = await saga.execute(ctx)
        assert result.error is not None
        assert "LLM offline" in result.error
        assert result.tool_name == "orchestrator"


# =========================================================================
# Message builders
# =========================================================================
class TestMessageBuilders:
    def test_build_router_message_with_user_only(self) -> None:
        ctx = ConversationContext(message_original="hello")
        msg = build_router_message(ctx)
        assert "hello" in msg
        assert "OCR" not in msg

    def test_build_router_message_with_ocr(self) -> None:
        ctx = ConversationContext(
            message_original="hi",
            ocr_text="texto da imagem",
            tags_encontradas=["TAG_A"],
        )
        msg = build_router_message(ctx)
        assert "hi" in msg
        assert "texto da imagem" in msg
        assert "TAG_A" in msg

    def test_build_router_message_empty(self) -> None:
        ctx = ConversationContext()
        msg = build_router_message(ctx)
        assert "vazia" in msg.lower() or "sem texto" in msg.lower()

    def test_build_rag_query(self) -> None:
        ctx = ConversationContext(
            message_original="tag X",
            ocr_text="ocr texto",
            tags_encontradas=["T1"],
        )
        q = build_rag_query(ctx)
        assert "tag X" in q
        assert "ocr texto" in q
        assert "T1" in q

    def test_build_agent_user_message_with_rag(self) -> None:
        ctx = ConversationContext(
            message_original="tag X",
            knowledge_context="RAG CTX",
            agent_route="pims",
            memory_context="> user: hi",
        )
        msg = build_agent_user_message(ctx)
        assert "RAG CTX" in msg
        assert "PERGUNTA DO USUÁRIO" in msg
        assert "tag X" in msg

    def test_build_agent_user_message_without_rag(self) -> None:
        ctx = ConversationContext(
            message_original="ola",
            knowledge_context="",
            agent_route="conversa_comum",
        )
        msg = build_agent_user_message(ctx)
        assert "ola" in msg
        assert "PERGUNTA DO USUÁRIO" not in msg


# =========================================================================
# Saga — EVENT_DRIVEN_ENABLED gate
# =========================================================================


class _FakeSettingsDisabled:
    """Fake settings object with EVENT_DRIVEN_ENABLED=False."""
    EVENT_DRIVEN_ENABLED: bool = False


class _FakeSettingsEnabled:
    """Fake settings object with EVENT_DRIVEN_ENABLED=True."""
    EVENT_DRIVEN_ENABLED: bool = True


class TestSagaEventDrivenGate:
    """Tests for EVENT_DRIVEN_ENABLED gate in ConversationSaga."""

    @pytest.mark.asyncio
    async def test_legacy_settings_none_uses_legacy_path(self) -> None:
        """settings=None preserves legacy: save_memory is called, events published."""
        save_memory_fn = AsyncMock()
        saga = _make_saga(save_memory_fn=save_memory_fn, settings=None)
        ctx = ConversationContext(
            conversation_id="user-1",
            message_original="hello",
            agent_output="world",
            agent_route="pims",
            tool_name="consultar_tag",
        )
        result = await saga._step_save_memory(ctx)
        save_memory_fn.assert_awaited_once()
        assert result is not None
        # Legacy path continues to produce ConversationMemorySaved
        # The mock event_publisher is None, so events are not actually published,
        # but we can verify the save_memory_fn was called (legacy path).

    @pytest.mark.asyncio
    async def test_legacy_settings_disabled_uses_legacy_path(self) -> None:
        """settings with EVENT_DRIVEN_ENABLED=False preserves legacy."""
        save_memory_fn = AsyncMock()
        saga = _make_saga(save_memory_fn=save_memory_fn, settings=_FakeSettingsDisabled())
        ctx = ConversationContext(
            conversation_id="user-1",
            message_original="hello",
            agent_output="world",
        )
        result = await saga._step_save_memory(ctx)
        save_memory_fn.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_edd_enabled_does_not_call_save_memory(self) -> None:
        """settings with EVENT_DRIVEN_ENABLED=True skips save_memory."""
        save_memory_fn = AsyncMock()
        saga = _make_saga(save_memory_fn=save_memory_fn, settings=_FakeSettingsEnabled())
        ctx = ConversationContext(
            conversation_id="user-1",
            message_original="hello",
            agent_output="world",
        )
        result = await saga._step_save_memory(ctx)
        save_memory_fn.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_edd_enabled_publishes_event(self) -> None:
        """settings with EVENT_DRIVEN_ENABLED=True publishes ConversationMemorySaveRequested."""
        from app.domain.events import ConversationMemorySaveRequested

        save_memory_fn = AsyncMock()
        events = AsyncMock()
        saga = _make_saga(
            save_memory_fn=save_memory_fn,
            event_publisher=events,
            settings=_FakeSettingsEnabled(),
        )
        ctx = ConversationContext(
            conversation_id="user-1",
            message_original="hello",
            agent_output="world",
        )
        result = await saga._step_save_memory(ctx)
        save_memory_fn.assert_not_called()
        # Verify publish was called with ConversationMemorySaveRequested
        # We can check the call args via the mock
        call_args = events.publish_to_conversation.call_args
        assert call_args is not None
        assert call_args[0][1].__class__ == ConversationMemorySaveRequested
        assert result is not None

    @pytest.mark.asyncio
    async def test_edd_enabled_still_publishes_user_message_recorded(self) -> None:
        """UserMessageRecorded continues to be published in step 1 regardless of gate."""
        # This test verifies that the step 1 (load_memory) behavior is unchanged.
        # UserMessageRecorded is published in _step_load_memory, not _step_save_memory.
        # We test that load_memory still works with enabled settings.
        events = AsyncMock()
        saga = _make_saga(
            event_publisher=events,
            settings=_FakeSettingsEnabled(),
        )
        ctx = ConversationContext(
            conversation_id="user-1",
            message_original="hello",
        )
        result = await saga._step_load_memory(ctx)
        assert result is not None
        call_args = events.publish_to_conversation.call_args
        assert call_args is not None
        from app.domain.projections import UserMessageRecorded
        assert call_args[0][1].__class__ == UserMessageRecorded
