"""
Orchestrator — main request lifecycle.

Flow (Etapa 3):
  POST /chat
    -> extract payload into ConversationContext
    -> ConversationSaga executes 6 steps:
       1. load_memory
       2. extract_ocr
       3. route
       4. retrieve_rag (if pims)
       5. run_agent
       6. save_memory
    -> build ChatResponse from final Context
    -> return ChatResponse

The old state: dict pattern is preserved as deprecated stubs for
backward compatibility with characterization tests (Etapa 0).
"""

from typing import Any

from app.agent.router import route_message
from app.agent.general_agent import run_general_agent
from app.agent.agent import run_agent
from app.application.sagas.conversation_saga import (
    ConversationContext,
    ConversationSaga,
    build_router_message as _saga_build_router_message,
    build_agent_user_message as _saga_build_agent_user_message,
)
from app.clients.qdrant_client import build_rag_context
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_memory_service import (
    append_memory_turns,
    format_memory_for_prompt,
    load_memory_turns,
)
from app.tasks.ocr_query import run_ocr_for_images


# ---------------------------------------------------------------------------
# Payload extraction helpers
# ---------------------------------------------------------------------------


def _get_payload_message(payload: ChatRequest) -> str:
    return (
        getattr(payload, "message", None)
        or getattr(payload, "mensagem", None)
        or getattr(payload, "input", None)
        or ""
    )


def _get_payload_images(payload: ChatRequest) -> list:
    return (
        getattr(payload, "images", None)
        or getattr(payload, "imagens", None)
        or []
    )


def _get_payload_user_id(payload: ChatRequest) -> str | None:
    return getattr(payload, "user_id", None)


def _get_payload_conversation_id(payload: ChatRequest) -> str | None:
    return (
        getattr(payload, "conversation_id", None)
        or getattr(payload, "user_id", None)
    )


# ---------------------------------------------------------------------------
# Memory adapters (wrap existing services for Saga injection)
# ---------------------------------------------------------------------------


class _MemoryAdapter:
    """Adapter: chat_memory_service -> ConversationMemory Protocol (v1 legacy)."""

    async def load_turns(self, conversation_id, max_turns=None):
        return await load_memory_turns(conversation_id, max_turns)

    async def append_turns(self, conversation_id, user_message, assistant_message, metadata=None):
        await append_memory_turns(conversation_id, user_message, assistant_message, metadata)

    def format_for_prompt(self, turns):
        return format_memory_for_prompt(turns)


class _MemoryAdapterV2:
    """Adapter: RedisConversationMemory -> ConversationMemory Protocol (v2 EventStore)."""

    def __init__(self, memory):
        self._memory = memory

    async def load_turns(self, conversation_id, max_turns=None):
        return await self._memory.load_turns(conversation_id, max_turns)

    async def append_turns(self, conversation_id, user_message, assistant_message, metadata=None):
        await self._memory.append_turns(conversation_id, user_message, assistant_message, metadata)

    def format_for_prompt(self, turns):
        return self._memory.format_for_prompt(turns)


class _OcrAdapter:
    """Adapter: run_ocr_for_images -> OcrService Protocol."""

    async def extract_batch(self, images):
        return await run_ocr_for_images(images)

    async def extract(self, image):
        results = await self.extract_batch([image])
        return results[0] if results else None


class _RagAdapter:
    """Adapter: build_rag_context -> KnowledgeRepository Protocol."""

    def build_context(self, query, top_k, include_fixed):
        return build_rag_context(
            query=query, top_k=top_k, include_fixed_chunk=include_fixed
        )

    def retrieve_relevant(self, query, top_k):
        from app.clients.qdrant_client import retrieve_relevant_chunks
        from dataclasses import dataclass

        @dataclass
        class _Chunk:
            chunk_number: int
            title: str
            content: str
            score: float

        raw = retrieve_relevant_chunks(query=query, top_k=top_k)
        return [_Chunk(**c) for c in raw]

    def get_fixed_chunk(self):
        from app.clients.qdrant_client import _load_fixed_chunk
        return _load_fixed_chunk()


# ---------------------------------------------------------------------------
# Saga construction
# ---------------------------------------------------------------------------


def _build_saga(event_publisher=None, event_store=None) -> ConversationSaga:
    """Wire up the Saga with production handlers.

    Args:
        event_publisher: Publisher for domain events. Uses NullEventPublisher if None.
        event_store: EventStore for conversation memory (v2). If None, uses v1 (legacy).
    """
    from app.application.sagas.event_publisher import NullEventPublisher

    # Memory adapter: use v2 if event_store provided, else v1
    if event_store is not None:
        from app.infrastructure.conversation.redis_memory_v2 import RedisConversationMemory
        memory_v2 = RedisConversationMemory(event_store=event_store)
        memory_adapter = _MemoryAdapterV2(memory_v2)
    else:
        memory_adapter = _MemoryAdapter()

    ocr_adapter = _OcrAdapter()
    rag_adapter = _RagAdapter()

    from app.application.queries.get_conversation_memory import GetConversationMemoryHandler
    from app.application.commands.extract_ocr import ExtractOcrHandler
    from app.application.commands.route_message import RouteMessageHandler
    from app.application.commands.retrieve_knowledge_context import RetrieveKnowledgeContextHandler
    from app.application.commands.run_agent_for_message import RunAgentForMessageHandler
    from app.application.commands.save_conversation_turn import SaveConversationTurnHandler

    return ConversationSaga(
        load_memory_fn=GetConversationMemoryHandler(memory=memory_adapter).handle,
        ocr_fn=ExtractOcrHandler(ocr_service=ocr_adapter).handle,
        route_fn=RouteMessageHandler(route_fn=route_message).handle,
        rag_fn=RetrieveKnowledgeContextHandler(knowledge_repo=rag_adapter).handle,
        run_agent_fn=RunAgentForMessageHandler(
            agent_fn=run_agent,
            general_agent_fn=run_general_agent,
        ).handle,
        save_memory_fn=SaveConversationTurnHandler(memory=memory_adapter).handle,
        event_publisher=event_publisher,
    )


# ---------------------------------------------------------------------------
# Main entry point (Etapa 3: uses ConversationSaga)
# ---------------------------------------------------------------------------


async def process_message(payload: ChatRequest) -> ChatResponse:
    """Main entry point — same signature, now uses Context + Saga with events."""
    message_original = _get_payload_message(payload)
    images = _get_payload_images(payload)
    user_id = _get_payload_user_id(payload)
    conversation_id = _get_payload_conversation_id(payload)

    # Build event publisher (uses NullEventPublisher by default)
    try:
        from app.infrastructure.event_store.in_memory import InMemoryEventStore
        from app.application.sagas.event_publisher import EventPublisherImpl
        _event_store = InMemoryEventStore()
        event_publisher = EventPublisherImpl(_event_store)
    except Exception:
        from app.application.sagas.event_publisher import NullEventPublisher
        event_publisher = NullEventPublisher()

    ctx = ConversationContext(
        user_id=user_id,
        conversation_id=conversation_id,
        message_original=message_original,
        images=images,
    )

    saga = _build_saga(event_publisher=event_publisher)
    ctx = await saga.execute(ctx)

    # Build response from Context
    if ctx.error:
        categoria = "erro_no_orchestrator"
        next_action = "orchestrator"
        tool_result = {"error": ctx.error}
        agent_trace: list[dict[str, Any]] = []
    elif ctx.agent_route:
        categoria = ctx.agent_route
        next_action = ctx.tool_name or "orchestrator"
        agent_trace = _build_trace(ctx.agent_messages)
        tool_result = {"agent_used": True, "agent_trace": agent_trace} if ctx.tool_name else None
    else:
        categoria = "conversa_comum"
        next_action = "general_agent"
        agent_trace = _build_trace(ctx.agent_messages)
        tool_result = {"agent_used": True, "agent_trace": agent_trace} if ctx.tool_name else None

    return ChatResponse(
        ok=ctx.error is None,
        user_id=ctx.user_id,
        message_original=message_original,
        processed_message=message_original,
        categoria=categoria,
        next_action=next_action,
        has_image=bool(images),
        skip_ocr=ctx.skip_ocr,
        ocr_text=ctx.ocr_text,
        tags_encontradas=ctx.tags_encontradas,
        tags_consultadas=[],
        ocr_results=ctx.ocr_extractions,
        tool_name=ctx.tool_name,
        tool_result=tool_result,
        agent_trace=agent_trace,
        output=ctx.agent_output,
        answer_generation_error=ctx.error,
    )


# ---------------------------------------------------------------------------
# Agent trace builder (preserved from old orchestrator)
# ---------------------------------------------------------------------------


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()

    parts_attr = getattr(content, "parts", None)
    if parts_attr is not None:
        text_parts: list[str] = []
        for part in parts_attr:
            if part is None:
                continue
            if getattr(part, "thought", False):
                continue
            text = getattr(part, "text", None)
            if text:
                text_parts.append(str(text))
        if text_parts:
            return "\n".join(text_parts).strip()

    if isinstance(content, list):
        parts_list: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts_list.append(str(text))
            else:
                parts_list.append(str(item))
        return "\n".join(parts_list).strip()

    return str(content).strip()


def build_safe_agent_trace(agent_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build agent trace from agent result dict (preserved for compatibility)."""
    messages = agent_result.get("messages", [])
    trace: list[dict[str, Any]] = []

    for msg in messages:
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        trace.append(
            {
                "type": msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "type", "unknown"),
                "name": msg.get("name") if isinstance(msg, dict) else getattr(msg, "name", None),
                "content": _content_to_text(content)[:1000],
                "tool_calls": msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None) or [],
            }
        )

    return trace


def _build_trace(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build agent trace from messages list."""
    trace: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    text_parts.append(str(part.get("text", "")))
                else:
                    text_parts.append(str(part))
            content = "\n".join(text_parts)
        trace.append({
            "type": msg.get("role", "unknown"),
            "name": msg.get("name"),
            "content": str(content)[:1000],
            "tool_calls": msg.get("tool_calls", []),
        })
    return trace


# ---------------------------------------------------------------------------
# Deprecated stubs (preserved for backward compatibility with Etapa 0 tests)
# These are no longer used in the main flow but exist so that the
# characterization tests which monkeypatch them can still run.
# ---------------------------------------------------------------------------


def build_router_message(state: dict) -> str:
    """Build router message from state dict (deprecated, use _saga_build_router_message)."""
    user_message = (state.get("message_original") or "").strip()
    ocr_text = (state.get("ocr_text") or "").strip()
    tags = state.get("tags_encontradas") or []

    parts: list[str] = []

    if user_message:
        parts.append(f"Mensagem do usuário:\n{user_message}")

    if ocr_text:
        parts.append(f"Texto OCR tratado:\n{ocr_text}")

    if tags:
        parts.append("Tags encontradas no OCR:\n" + "\n".join(tags))

    if not parts:
        parts.append("Mensagem do usuário vazia ou sem texto útil.")

    return "\n\n".join(parts).strip()


def build_agent_user_message(state: dict) -> str:
    """Build agent user message from state dict (deprecated)."""
    memory_context = (state.get("memory_context") or "").strip()
    message = build_router_message(state)

    parts: list[str] = []
    if memory_context:
        parts.append(memory_context)
    parts.append(message)

    return "\n\n".join(parts).strip()


async def _ocr_step(state: dict) -> dict:
    """OCR step (deprecated stub for backward compatibility)."""
    images = state.get("images") or []

    if not images:
        state["skip_ocr"] = True
        state["ocr_results"] = []
        state["ocr_text"] = None
        state["tags_encontradas"] = []
        return state

    ocr_results = await run_ocr_for_images(images)

    ocr_text_parts: list[str] = []
    tags_encontradas: list[str] = []

    for result in ocr_results:
        ocr_text_parts.append(f"[Imagem {result.image_index}]\n{result.resultado}")
        for tag in result.tags_encontradas:
            if tag not in tags_encontradas:
                tags_encontradas.append(tag)

    state["skip_ocr"] = False
    state["ocr_results"] = ocr_results
    state["ocr_text"] = "\n\n".join(ocr_text_parts).strip()
    state["tags_encontradas"] = tags_encontradas

    return state


async def _load_memory(state: dict) -> dict:
    """Memory load (deprecated stub)."""
    conversation_id = state.get("conversation_id")
    turns = await load_memory_turns(conversation_id=conversation_id)
    state["memory_turns"] = turns
    state["memory_context"] = format_memory_for_prompt(turns) or None
    return state


async def _save_memory(state: dict) -> dict:
    """Memory save (deprecated stub)."""
    conversation_id = state.get("conversation_id")
    user_message = state.get("message_original") or ""
    assistant_message = state.get("output") or ""

    if not conversation_id:
        return state

    if not user_message and not assistant_message:
        return state

    await append_memory_turns(
        conversation_id=conversation_id,
        user_message=user_message,
        assistant_message=assistant_message,
        metadata={
            "user_id": state.get("user_id"),
            "categoria": state.get("categoria"),
            "next_action": state.get("next_action"),
            "tool_name": state.get("tool_name"),
        },
    )

    return state
