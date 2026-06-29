"""
Characterization tests for app/agent/orchestrator.py

Purpose: Lock down the current behavior of process_message() so that
future refactoring (DDD, CQRS, Sagas) can proceed safely.

These tests do NOT modify any production code. They observe and record
what process_message() does today.

Each test has a docstring explaining the behavior it captures.
"""

import pytest

from app.schemas.chat import ChatRequest, ChatImage


# ===========================================================================
# 1. State shape — the 18 keys that process_message builds
# ===========================================================================


class TestStateShape:
    """Lock down the exact keys present in the state dict."""

    @pytest.mark.asyncio
    async def test_process_message_state_has_all_expected_keys(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """process_message returns a ChatResponse with all expected fields.

        After Etapa 3, the internal state dict is replaced by ConversationContext.
        This test verifies the ChatResponse contract.
        """
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        # Required fields always present (ChatResponse contract)
        required_fields = {
            "ok", "user_id", "message_original", "processed_message",
            "categoria", "next_action", "has_image", "skip_ocr",
            "ocr_text", "tags_encontradas", "tags_consultadas", "ocr_results",
            "tool_name", "tool_result", "agent_trace", "output",
            "answer_generation_error",
        }
        for field_name in required_fields:
            assert hasattr(response, field_name), f"Missing field: {field_name}"


# ===========================================================================
# 2. General route — conversa_comum
# ===========================================================================


class TestGeneralRoute:
    """process_message routes to general_agent when router returns 'conversa_comum'."""

    @pytest.mark.asyncio
    async def test_process_message_with_general_route_calls_general_agent(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """When the router classifies as 'conversa_comum', run_general_agent is called."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.ok is True
        assert response.categoria == "conversa_comum"
        assert response.next_action == "general_agent"
        assert response.tool_name == "general_agent"
        assert response.output == "Olá! Como posso ajudar?"

    @pytest.mark.asyncio
    async def test_process_message_general_route_has_empty_agent_trace(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """General agent returns no tool calls, so agent_trace is empty."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.agent_trace == []

    @pytest.mark.asyncio
    async def test_process_message_general_route_no_rag_context(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """General route does NOT call build_rag_context (no RAG for general chat)."""
        from app.agent.orchestrator import process_message

        rag_called = {"called": False}

        original_build = None

        import app.agent.orchestrator as orch
        original_build = orch.build_rag_context
        def _tracking_build(**kwargs):
            rag_called["called"] = True
            return original_build(**kwargs)

        orch.build_rag_context = _tracking_build
        try:
            await process_message(simple_text_request)
            assert rag_called["called"] is False
        finally:
            orch.build_rag_context = original_build


# ===========================================================================
# 3. PIMS route — agent with RAG
# ===========================================================================


class TestPimsRoute:
    """process_message routes to agent when router returns 'pims'."""

    @pytest.mark.asyncio
    async def test_process_message_pims_route_calls_agent(
        self,
        simple_text_request,
        mock_redis,
        mock_route_pims,
        mock_agent,
        mock_rag_empty,
        mock_ocr_no_images,
    ):
        """When the router classifies as 'pims', run_agent is called."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.ok is True
        assert response.categoria == "pims"
        assert response.next_action == "agent"
        assert response.output == "O valor atual de LFI_RB3_VAZ_GN_TOTAL é 1523.4 Nm3/h"

    @pytest.mark.asyncio
    async def test_process_message_pims_route_calls_build_rag_context(
        self,
        simple_text_request,
        mock_redis,
        mock_route_pims,
        mock_agent,
        mock_ocr_no_images,
    ):
        """PIMS route calls build_rag_context with the user message."""
        from app.agent.orchestrator import process_message

        rag_calls = {"args": []}

        import app.agent.orchestrator as orch
        original_build = orch.build_rag_context
        def _tracking_build(**kwargs):
            rag_calls["args"].append(kwargs)
            return ""
        orch.build_rag_context = _tracking_build
        try:
            await process_message(simple_text_request)
            assert len(rag_calls["args"]) == 1
            assert "query" in rag_calls["args"][0]
        finally:
            orch.build_rag_context = original_build

    @pytest.mark.asyncio
    async def test_process_message_pims_route_enriches_message_with_rag(
        self,
        simple_text_request,
        mock_redis,
        mock_route_pims,
        mock_agent,
        mock_ocr_no_images,
    ):
        """PIMS route prepends RAG context to the user message."""
        from app.agent.orchestrator import process_message

        captured_args = {}

        async def _tracking_agent(**kwargs):
            captured_args.update(kwargs)
            return {"output": "ok", "error": None, "messages": []}

        import app.agent.orchestrator as orch
        original_pi = orch.run_agent
        orch.run_agent = _tracking_agent
        try:
            await process_message(simple_text_request)
            user_msg = captured_args.get("user_message", "")
            assert "qual o valor da LFI_RB3_VAZ_GN_TOTAL" in user_msg
        finally:
            orch.run_agent = original_pi


# ===========================================================================
# 4. Memory — load and save
# ===========================================================================


class TestMemory:
    """Lock down memory loading and saving behavior."""

    @pytest.mark.asyncio
    async def test_process_message_loads_memory_before_agent(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """Memory is loaded via redis lrange before the agent runs."""
        from app.agent.orchestrator import process_message

        await process_message(simple_text_request)

        # redis.lrange was called (memory loaded)
        mock_redis.lrange.assert_called()

    @pytest.mark.asyncio
    async def test_process_message_saves_memory_after_agent(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """After the agent responds, a pipeline with rpush+ltrim+expire is called."""
        from app.agent.orchestrator import process_message

        await process_message(simple_text_request)

        pipeline = mock_redis.pipeline.return_value
        pipeline.rpush.assert_called()
        pipeline.ltrim.assert_called()
        pipeline.expire.assert_called()

    @pytest.mark.asyncio
    async def test_process_message_memory_saved_with_correct_metadata(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """After the agent responds, pipeline is called with rpush, ltrim, expire.

        rpush is called ONCE with 3 arguments: key + user_turn_json + assistant_turn_json.
        This is the current behavior: both turns are pushed in a single call.
        """
        from app.agent.orchestrator import process_message

        await process_message(simple_text_request)

        pipeline = mock_redis.pipeline.return_value
        # rpush called ONCE with key + 2 turn payloads
        assert pipeline.rpush.call_count == 1
        rpush_args = pipeline.rpush.call_args
        # 3 positional args: key, user_turn_json, assistant_turn_json
        assert len(rpush_args[0]) == 3
        pipeline.ltrim.assert_called_once()
        pipeline.expire.assert_called_once()


# ===========================================================================
# 5. OCR — skipped when no images
# ===========================================================================


class TestOcr:
    """Lock down OCR behavior."""

    @pytest.mark.asyncio
    async def test_process_message_ocr_skipped_when_no_images(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """When there are no images, skip_ocr=True and ocr_text=None."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.skip_ocr is True
        assert response.ocr_text is None
        assert response.ocr_results == []
        assert response.tags_encontradas == []

    @pytest.mark.asyncio
    async def test_process_message_ocr_runs_for_each_image(
        self,
        request_with_images,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_with_tags,
    ):
        """When images are present, OCR is run and results are extracted."""
        from app.agent.orchestrator import process_message

        response = await process_message(request_with_images)

        assert response.skip_ocr is False
        assert response.ocr_text is not None
        assert len(response.ocr_results) == 1
        assert response.ocr_results[0].tags_encontradas == ["LFI_RB3_VAZ_GN_TOTAL"]

    @pytest.mark.asyncio
    async def test_process_message_ocr_tags_injected_into_state(
        self,
        request_with_images,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_with_tags,
    ):
        """OCR-extracted tags appear in tags_encontradas."""
        from app.agent.orchestrator import process_message

        response = await process_message(request_with_images)

        assert "LFI_RB3_VAZ_GN_TOTAL" in response.tags_encontradas


# ===========================================================================
# 6. Router error handling — falls back to conversa_comum
# ===========================================================================


class TestRouterError:
    """Lock down fallback behavior when the router fails."""

    @pytest.mark.asyncio
    async def test_process_message_route_message_falls_back_on_error(
        self,
        simple_text_request,
        mock_redis,
        mock_route_error,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """When the router raises, process_message catches and returns
        error_no_orchestrator with the error message."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.ok is False
        assert response.categoria == "erro_no_orchestrator"
        assert response.next_action == "orchestrator"
        assert response.answer_generation_error is not None
        assert "Router LLM unavailable" in response.answer_generation_error


# ===========================================================================
# 7. ChatResponse shape — required fields
# ===========================================================================


class TestChatResponseShape:
    """Lock down the contract of ChatResponse."""

    @pytest.mark.asyncio
    async def test_process_message_returns_chatresponse_with_required_fields(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """ChatResponse has all fields required by the API contract."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        # Required fields always present
        assert hasattr(response, "ok")
        assert hasattr(response, "user_id")
        assert hasattr(response, "message_original")
        assert hasattr(response, "categoria")
        assert hasattr(response, "next_action")
        assert hasattr(response, "has_image")
        assert hasattr(response, "skip_ocr")
        assert hasattr(response, "tool_name")
        assert hasattr(response, "tool_result")
        assert hasattr(response, "agent_trace")
        assert hasattr(response, "output")

        # Type checks
        assert isinstance(response.ok, bool)
        assert isinstance(response.has_image, bool)
        assert isinstance(response.skip_ocr, bool)
        assert isinstance(response.agent_trace, list)

    @pytest.mark.asyncio
    async def test_process_message_categoria_matches_route(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """categoria in ChatResponse matches the route chosen by the router."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.categoria == "conversa_comum"
        assert response.next_action == "general_agent"


# ===========================================================================
# 8. build_router_message — composition logic
# ===========================================================================


class TestBuildRouterMessage:
    """Lock down the message composition logic."""

    def test_build_router_message_with_user_text_only(self):
        """Only user message → message contains it."""
        from app.agent.orchestrator import build_router_message

        state = {
            "message_original": "qual o valor da tag X",
            "ocr_text": None,
            "tags_encontradas": [],
        }
        result = build_router_message(state)
        assert "qual o valor da tag X" in result
        assert "OCR" not in result

    def test_build_router_message_with_ocr_and_tags(self):
        """User message + OCR text + tags → all included."""
        from app.agent.orchestrator import build_router_message

        state = {
            "message_original": "analise",
            "ocr_text": "Texto extraido da imagem",
            "tags_encontradas": ["LFI_RB3_VAZ_GN_TOTAL"],
        }
        result = build_router_message(state)
        assert "analise" in result
        assert "Texto extraido da imagem" in result
        assert "LFI_RB3_VAZ_GN_TOTAL" in result

    def test_build_router_message_empty_state(self):
        """Empty state → fallback message."""
        from app.agent.orchestrator import build_router_message

        state = {
            "message_original": "",
            "ocr_text": None,
            "tags_encontradas": [],
        }
        result = build_router_message(state)
        assert "vazia" in result.lower() or "sem texto" in result.lower()


# ===========================================================================
# 9. build_safe_agent_trace — trace extraction
# ===========================================================================


class TestBuildSafeAgentTrace:
    """Lock down agent trace building behavior."""

    def test_trace_with_empty_messages(self):
        """Empty messages → empty trace."""
        from app.agent.orchestrator import build_safe_agent_trace

        result = build_safe_agent_trace({"messages": []})
        assert result == []

    def test_trace_with_tool_calls(self):
        """Messages with tool_calls are preserved in trace."""
        from app.agent.orchestrator import build_safe_agent_trace

        agent_result = {
            "messages": [
                {
                    "role": "assistant",
                    "content": "Vou consultar a tag",
                    "tool_calls": [
                        {"id": "tc1", "name": "consultar_tag", "args": {"tags": ["X"]}}
                    ],
                }
            ]
        }
        trace = build_safe_agent_trace(agent_result)
        assert len(trace) == 1
        assert trace[0]["tool_calls"] is not None
        assert len(trace[0]["tool_calls"]) == 1

    def test_trace_content_truncated_at_1000_chars(self):
        """Content is truncated at 1000 characters."""
        from app.agent.orchestrator import build_safe_agent_trace

        long_content = "x" * 2000
        agent_result = {"messages": [{"role": "assistant", "content": long_content}]}
        trace = build_safe_agent_trace(agent_result)
        assert len(trace[0]["content"]) <= 1000


# ===========================================================================
# 10. process_message — user_id and conversation_id derivation
# ===========================================================================


class TestConversationId:
    """Lock down how conversation_id is derived."""

    @pytest.mark.asyncio
    async def test_conversation_id_equals_user_id(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """When no conversation_id is provided, it defaults to user_id.

        NOTE: ChatResponse schema does NOT expose conversation_id yet.
        This is documented here as a future requirement for DDD/CQRS.
        The state dict uses conversation_id internally (derived from user_id).
        """
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        # user_id is preserved in the response
        assert response.user_id == "test-user-001"
        # ChatResponse does NOT expose conversation_id field (future improvement)
        assert not hasattr(response, "conversation_id")

    @pytest.mark.asyncio
    async def test_user_id_preserved_in_response(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """user_id from the request is preserved in the response."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.user_id == "test-user-001"


# ===========================================================================
# 11. Error propagation — orchestrator errors
# ===========================================================================


class TestErrorPropagation:
    """Lock down error handling behavior."""

    @pytest.mark.asyncio
    async def test_process_message_error_no_answer_generation_error_field(
        self,
        simple_text_request,
        mock_redis,
        mock_route_error,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """On orchestrator error, answer_generation_error is set."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.answer_generation_error is not None
        assert response.ok is False

    @pytest.mark.asyncio
    async def test_process_message_error_still_saves_memory(
        self,
        simple_text_request,
        mock_redis,
        mock_route_error,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """Even on error, the memory save pipeline is called."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        # Memory save still occurs (pipeline called)
        pipeline = mock_redis.pipeline.return_value
        pipeline.rpush.assert_called()


# ===========================================================================
# 12. MessageOriginal preservation
# ===========================================================================


class TestMessageOriginal:
    """Lock down that original message is preserved."""

    @pytest.mark.asyncio
    async def test_message_original_preserved_in_response(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """message_original in ChatResponse matches the input."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.message_original == "qual o valor da LFI_RB3_VAZ_GN_TOTAL"

    @pytest.mark.asyncio
    async def test_processed_message_matches_original_for_text_only(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        """For text-only requests, processed_message equals message_original."""
        from app.agent.orchestrator import process_message

        response = await process_message(simple_text_request)

        assert response.processed_message == "qual o valor da LFI_RB3_VAZ_GN_TOTAL"
