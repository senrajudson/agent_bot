"""Unit tests for build_chat_response (Prompt 5 Ciclo 1)."""
from __future__ import annotations

from app.application.sagas.conversation_saga import ConversationContext
from app.application.use_cases.build_chat_response import build_chat_response


class TestBuildChatResponse:
    def test_error_branch(self) -> None:
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="hi",
            images=[],
            error="boom",
        )
        resp = build_chat_response(ctx)

        assert resp.ok is False
        assert resp.user_id == "u1"
        assert resp.message_original == "hi"
        assert resp.processed_message == "hi"
        assert resp.categoria == "erro_no_orchestrator"
        assert resp.next_action == "orchestrator"
        assert resp.has_image is False
        assert resp.skip_ocr is True
        assert resp.ocr_text is None
        assert resp.tags_encontradas == []
        assert resp.tags_consultadas == []
        assert resp.ocr_results == []
        assert resp.tool_name is None
        assert resp.tool_result == {"error": "boom"}
        assert resp.agent_trace == []
        assert resp.output is None
        assert resp.answer_generation_error == "boom"

    def test_agent_route_branch(self) -> None:
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="tag X",
            images=[],
            agent_route="pims",
            agent_output="resposta",
            tool_name="agent",
            agent_messages=[{"role": "user", "content": "tag X"}],
        )
        resp = build_chat_response(ctx)

        assert resp.ok is True
        assert resp.user_id == "u1"
        assert resp.message_original == "tag X"
        assert resp.processed_message == "tag X"
        assert resp.categoria == "pims"
        assert resp.next_action == "agent"
        assert resp.has_image is False
        assert resp.tool_name == "agent"
        assert resp.tool_result is not None
        assert resp.tool_result["agent_used"] is True
        assert resp.tool_result["agent_trace"] == resp.agent_trace
        assert len(resp.agent_trace) == 1
        assert resp.agent_trace[0]["type"] == "user"
        assert resp.output == "resposta"
        assert resp.answer_generation_error is None

    def test_general_branch(self) -> None:
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="oi",
            images=[],
            agent_output="ola!",
            tool_name="general_agent",
            agent_messages=[{"role": "user", "content": "oi"}],
        )
        resp = build_chat_response(ctx)

        assert resp.ok is True
        assert resp.categoria == "conversa_comum"
        assert resp.next_action == "general_agent"
        assert resp.tool_result is not None
        assert resp.tool_result["agent_used"] is True
        assert resp.output == "ola!"
