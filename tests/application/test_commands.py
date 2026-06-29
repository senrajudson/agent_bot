"""Tests for application Commands and Handlers."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.application.commands.base import Command, CommandHandler
from app.application.commands.extract_ocr import (
    ExtractOcr,
    ExtractOcrHandler,
    ExtractOcrResult,
)
from app.application.commands.invoke_mcp_tool import (
    InvokeMcpTool,
    InvokeMcpToolHandler,
    InvokeMcpToolResult,
)
from app.application.commands.retrieve_knowledge_context import (
    RetrieveKnowledgeContext,
    RetrieveKnowledgeContextHandler,
    RetrieveKnowledgeContextResult,
)
from app.application.commands.route_message import (
    RouteMessage,
    RouteMessageHandler,
    RouteMessageResult,
)
from app.application.commands.run_agent_for_message import (
    RunAgentForMessage,
    RunAgentForMessageHandler,
    RunAgentForMessageResult,
)
from app.application.commands.save_conversation_turn import (
    SaveConversationTurn,
    SaveConversationTurnHandler,
)
from app.domain.enums import AgentRoute


# =========================================================================
# Base abstractions
# =========================================================================
class TestCommandBase:
    def test_command_is_frozen_dataclass(self) -> None:
        @dataclass(frozen=True)
        class DummyCommand(Command):
            value: str

        cmd = DummyCommand(value="test")
        assert cmd.value == "test"
        with pytest.raises(AttributeError):
            cmd.value = "other"  # type: ignore[misc]


# =========================================================================
# ExtractOcr
# =========================================================================
class TestExtractOcr:
    @pytest.mark.asyncio
    async def test_empty_images_returns_empty(self, mock_ocr_service: AsyncMock) -> None:
        handler = ExtractOcrHandler(mock_ocr_service)
        result = await handler.handle(ExtractOcr(images=[]))
        assert result.extractions == []

    @pytest.mark.asyncio
    async def test_delegates_to_ocr_service(self, mock_ocr_service: AsyncMock) -> None:
        handler = ExtractOcrHandler(mock_ocr_service)
        fake_image = object()  # placeholder
        result = await handler.handle(ExtractOcr(images=[fake_image]))
        mock_ocr_service.extract_batch.assert_awaited_once_with([fake_image])
        assert len(result.extractions) == 1

    @pytest.mark.asyncio
    async def test_returns_extractions(self, mock_ocr_service: AsyncMock) -> None:
        handler = ExtractOcrHandler(mock_ocr_service)
        result = await handler.handle(ExtractOcr(images=[object()]))
        assert result.extractions[0].tags == ["LFI_RB3_VAZ_GN_TOTAL"]


# =========================================================================
# RouteMessage
# =========================================================================
class TestRouteMessage:
    @pytest.mark.asyncio
    async def test_delegates_to_route_fn(self, mock_route_fn: AsyncMock) -> None:
        handler = RouteMessageHandler(route_fn=mock_route_fn)
        result = await handler.handle(RouteMessage(user_message="hello"))
        mock_route_fn.assert_awaited_once_with(user_message="hello")
        assert result.route == AgentRoute.PIMS

    @pytest.mark.asyncio
    async def test_returns_agent_route_enum(self, mock_route_fn: AsyncMock) -> None:
        handler = RouteMessageHandler(route_fn=mock_route_fn)
        result = await handler.handle(RouteMessage(user_message="test"))
        assert isinstance(result.route, AgentRoute)


# =========================================================================
# RunAgentForMessage
# =========================================================================
class TestRunAgentForMessage:
    @pytest.mark.asyncio
    async def test_pims_route_calls_agent(
        self, mock_agent_fn: AsyncMock, mock_general_agent_fn: AsyncMock
    ) -> None:
        handler = RunAgentForMessageHandler(
            agent_fn=mock_agent_fn,
            general_agent_fn=mock_general_agent_fn,
        )
        cmd = RunAgentForMessage(
            user_message="tag X",
            user_id="u1",
            session_id="s1",
            route=AgentRoute.PIMS,
        )
        result = await handler.handle(cmd)
        mock_agent_fn.assert_awaited_once()
        mock_general_agent_fn.assert_not_awaited()
        assert result.tool_name == "agent"
        assert result.output == "O valor e 1523.4 Nm3/h"

    @pytest.mark.asyncio
    async def test_general_route_calls_general_agent(
        self, mock_agent_fn: AsyncMock, mock_general_agent_fn: AsyncMock
    ) -> None:
        handler = RunAgentForMessageHandler(
            agent_fn=mock_agent_fn,
            general_agent_fn=mock_general_agent_fn,
        )
        cmd = RunAgentForMessage(
            user_message="ola",
            user_id="u1",
            session_id="s1",
            route=AgentRoute.GENERAL_CHAT,
        )
        result = await handler.handle(cmd)
        mock_general_agent_fn.assert_awaited_once()
        mock_agent_fn.assert_not_awaited()
        assert result.tool_name == "general_agent"
        assert result.output == "Ola! Como posso ajudar?"

    @pytest.mark.asyncio
    async def test_result_fields(
        self, mock_agent_fn: AsyncMock, mock_general_agent_fn: AsyncMock
    ) -> None:
        handler = RunAgentForMessageHandler(
            agent_fn=mock_agent_fn,
            general_agent_fn=mock_general_agent_fn,
        )
        result = await handler.handle(
            RunAgentForMessage(
                user_message="x", user_id="u1", session_id="s1", route=AgentRoute.PIMS
            )
        )
        assert result.error is None
        assert isinstance(result.messages, list)


# =========================================================================
# RetrieveKnowledgeContext
# =========================================================================
class TestRetrieveKnowledgeContext:
    @pytest.mark.asyncio
    async def test_delegates_to_knowledge_repo(self, mock_knowledge_repo: AsyncMock) -> None:
        handler = RetrieveKnowledgeContextHandler(mock_knowledge_repo)
        result = await handler.handle(
            RetrieveKnowledgeContext(query="valor da tag X")
        )
        mock_knowledge_repo.build_context.assert_called_once()
        mock_knowledge_repo.retrieve_relevant.assert_called_once()
        assert result.context == "FAKE CONTEXT"
        assert result.chunks_used == [1]


# =========================================================================
# SaveConversationTurn
# =========================================================================
class TestSaveConversationTurn:
    @pytest.mark.asyncio
    async def test_delegates_to_memory(self, mock_conversation_memory: AsyncMock) -> None:
        handler = SaveConversationTurnHandler(mock_conversation_memory)
        await handler.handle(
            SaveConversationTurn(
                conversation_id="conv-1",
                user_message="hi",
                assistant_message="hello",
            )
        )
        mock_conversation_memory.append_turns.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_when_empty_conversation_id(self, mock_conversation_memory: AsyncMock) -> None:
        handler = SaveConversationTurnHandler(mock_conversation_memory)
        await handler.handle(
            SaveConversationTurn(
                conversation_id="",
                user_message="hi",
                assistant_message="hello",
            )
        )
        mock_conversation_memory.append_turns.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_noop_when_empty_messages(self, mock_conversation_memory: AsyncMock) -> None:
        handler = SaveConversationTurnHandler(mock_conversation_memory)
        await handler.handle(
            SaveConversationTurn(
                conversation_id="conv-1",
                user_message="",
                assistant_message="",
            )
        )
        mock_conversation_memory.append_turns.assert_not_awaited()


# =========================================================================
# InvokeMcpTool (placeholder)
# =========================================================================
class TestInvokeMcpTool:
    @pytest.mark.asyncio
    async def test_raises_not_implemented(self) -> None:
        handler = InvokeMcpToolHandler()
        with pytest.raises(NotImplementedError, match="placeholder"):
            await handler.handle(InvokeMcpTool(tool_name="consultar_tag", args={}))
