"""Conversation Saga — orchestrates the /chat request lifecycle.

Replaces the state: dict[str, Any] pattern in orchestrator.py with:
- ConversationContext: typed, frozen dataclass holding per-request data
- ConversationSaga: explicit sequence of steps (each step is a Command invocation)

Design:
- Context is FROZEN after each step (immutability per step)
- Each step is a small method (≤20 lines)
- Saga does not know about httpx, redis, qdrant, litellm, google.adk
- All side effects go through injected callables
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConversationContext:
    """Typed per-request state, replacing state: dict[str, Any].

    Immutable: use ``replace(ctx, field=new_value)`` to create a new Context.
    """

    # Identifiers
    user_id: str | None = None
    conversation_id: str | None = None

    # Input
    message_original: str = ""
    images: list = field(default_factory=list)

    # OCR
    ocr_text: str | None = None
    ocr_extractions: list = field(default_factory=list)
    tags_encontradas: list[str] = field(default_factory=list)
    skip_ocr: bool = True

    # Memory
    memory_turns: list = field(default_factory=list)
    memory_context: str | None = None

    # Routing
    agent_route: str | None = None

    # RAG
    knowledge_context: str = ""

    # Agent
    agent_output: str | None = None
    agent_error: str | None = None
    agent_messages: list[dict[str, Any]] = field(default_factory=list)
    tool_name: str | None = None

    # Error state
    error: str | None = None


# ---------------------------------------------------------------------------
# Saga
# ---------------------------------------------------------------------------

# Type aliases for injected callables
LoadMemoryFn = Callable[..., Awaitable[Any]]
OcrFn = Callable[..., Awaitable[Any]]
RouteFn = Callable[..., Awaitable[Any]]
RagFn = Callable[..., Awaitable[Any]]
RunAgentFn = Callable[..., Awaitable[Any]]
SaveMemoryFn = Callable[..., Awaitable[None]]


class ConversationSaga:
    """Orchestrates the /chat request lifecycle as a sequence of steps.

    Steps (in order):
        1. load_memory     — GetConversationMemory
        2. extract_ocr     — ExtractOcr
        3. route           — RouteMessage
        4. retrieve_rag    — RetrieveKnowledgeContext (if pims)
        5. run_agent       — RunAgentForMessage
        6. save_memory     — SaveConversationTurn

    Each step receives a Context and returns a new Context.
    On error, the saga stops and records the error in the Context.
    """

    def __init__(
        self,
        load_memory_fn: LoadMemoryFn,
        ocr_fn: OcrFn,
        route_fn: RouteFn,
        rag_fn: RagFn,
        run_agent_fn: RunAgentFn,
        save_memory_fn: SaveMemoryFn,
        event_publisher=None,
    ) -> None:
        self._load_memory = load_memory_fn
        self._ocr = ocr_fn
        self._route = route_fn
        self._rag = rag_fn
        self._run_agent = run_agent_fn
        self._save_memory = save_memory_fn
        self._events = event_publisher

    async def execute(self, ctx: ConversationContext) -> ConversationContext:
        """Run all steps in order, stopping on error.

        Memory is ALWAYS saved (last step), even on error.
        This matches the original orchestrator behavior.
        """
        steps = [
            self._step_load_memory,
            self._step_extract_ocr,
            self._step_route,
            self._step_retrieve_rag,
            self._step_run_agent,
        ]
        for step in steps:
            try:
                ctx = await step(ctx)
            except Exception as exc:
                ctx = _record_error(ctx, exc)
                await _publish_error(self, ctx, exc)
                break
            if ctx.error is not None:
                break

        # Always save memory, even on error
        try:
            ctx = await self._step_save_memory(ctx)
        except Exception:
            pass  # Memory save failure is non-critical

        return ctx

    # -----------------------------------------------------------------------
    # Event publishing helper
    # -----------------------------------------------------------------------

    async def _publish(self, ctx: ConversationContext, event) -> None:
        """Publish an event to the conversation stream (fire-and-forget)."""
        if self._events is not None:
            cid = ctx.conversation_id or "anonymous"
            fields = {k: v for k, v in event.__dict__.items() if k != "conversation_id"}
            event_with_conversation = type(event)(**fields, conversation_id=cid)
            try:
                await self._events.publish_to_conversation(cid, event_with_conversation)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Steps
    # -----------------------------------------------------------------------

    async def _step_load_memory(self, ctx: ConversationContext) -> ConversationContext:
        if not ctx.conversation_id:
            return ctx
        from app.application.queries.get_conversation_memory import (
            GetConversationMemory,
        )

        result = await self._load_memory(
            GetConversationMemory(conversation_id=ctx.conversation_id)
        )
        new_ctx = replace(
            ctx,
            memory_turns=result.turns,
            memory_context=result.context or None,
        )
        from app.domain.events import ConversationMemoryLoaded
        await self._publish(ctx, ConversationMemoryLoaded(
            turns_count=len(result.turns),
            max_turns=8,
        ))
        # Also publish UserMessageRecorded for event sourcing
        from datetime import datetime
        from app.domain.projections import UserMessageRecorded
        await self._publish(ctx, UserMessageRecorded(
            content=ctx.message_original or "",
            created_at=datetime.utcnow().isoformat(),
            metadata={"conversation_id": ctx.conversation_id or ""},
        ))
        return new_ctx

    async def _step_extract_ocr(self, ctx: ConversationContext) -> ConversationContext:
        from app.application.commands.extract_ocr import ExtractOcr

        if not ctx.images:
            new_ctx = replace(
                ctx,
                skip_ocr=True,
                ocr_text=None,
                ocr_extractions=[],
                tags_encontradas=[],
            )
            return new_ctx
        result = await self._ocr(ExtractOcr(images=ctx.images))
        ocr_text_parts: list[str] = []
        tags: list[str] = []
        for ext in result.extractions:
            ext_text = getattr(ext, "text", None) or getattr(ext, "resultado", "") or ""
            ocr_text_parts.append(f"[Imagem {ext.image_index}]\n{ext_text}")
            ext_tags = getattr(ext, "tags", None) or getattr(ext, "tags_encontradas", []) or []
            for tag in ext_tags:
                if tag not in tags:
                    tags.append(tag)
        new_ctx = replace(
            ctx,
            skip_ocr=False,
            ocr_extractions=result.extractions,
            ocr_text="\n\n".join(ocr_text_parts).strip() or None,
            tags_encontradas=tags,
        )
        from app.domain.events import OcrExtractionCompleted
        await self._publish(ctx, OcrExtractionCompleted(
            message_id=ctx.message_original[:50] if ctx.message_original else "",
            image_count=len(ctx.images),
            tags_found=tags,
            total_text_length=sum(len(t) for t in ocr_text_parts),
        ))
        return new_ctx

    async def _step_route(self, ctx: ConversationContext) -> ConversationContext:
        from app.application.commands.route_message import RouteMessage

        router_msg = build_router_message(ctx)
        result = await self._route(RouteMessage(user_message=router_msg))
        new_ctx = replace(ctx, agent_route=result.route.value)
        from app.domain.events import AgentRouteSelected
        await self._publish(ctx, AgentRouteSelected(
            message_id=ctx.message_original[:50] if ctx.message_original else "",
            route=result.route.value,
        ))
        return new_ctx

    async def _step_retrieve_rag(self, ctx: ConversationContext) -> ConversationContext:
        if ctx.agent_route != "pims":
            return ctx
        from app.application.commands.retrieve_knowledge_context import (
            RetrieveKnowledgeContext,
        )

        rag_query = build_rag_query(ctx)
        result = await self._rag(
            RetrieveKnowledgeContext(query=rag_query, top_k=3)
        )
        new_ctx = replace(ctx, knowledge_context=result.context)
        from app.domain.events import RagContextRetrieved
        await self._publish(ctx, RagContextRetrieved(
            message_id=ctx.message_original[:50] if ctx.message_original else "",
            query_length=len(rag_query),
            chunks_retrieved=len(result.chunks_used),
            fixed_chunk_included=True,
        ))
        return new_ctx

    async def _step_run_agent(self, ctx: ConversationContext) -> ConversationContext:
        from app.application.commands.run_agent_for_message import (
            RunAgentForMessage,
        )

        if ctx.agent_route is None:
            return ctx
        from app.domain.events import AgentRunStarted
        run_id = ctx.conversation_id or "default"
        await self._publish(ctx, AgentRunStarted(
            run_id=run_id,
            agent_type="pi" if ctx.agent_route == "pims" else "general",
            route=ctx.agent_route,
            message_id=ctx.message_original[:50] if ctx.message_original else "",
        ))
        user_msg = build_agent_user_message(ctx)
        result = await self._run_agent(
            RunAgentForMessage(
                user_message=user_msg,
                user_id=ctx.user_id or "default_user",
                session_id=ctx.conversation_id or "default",
                route=ctx.agent_route,
                memory_context=ctx.memory_context,
            )
        )
        new_ctx = replace(
            ctx,
            agent_output=result.output or "Não consegui gerar uma resposta.",
            agent_error=result.error,
            agent_messages=result.messages,
            tool_name=result.tool_name,
        )
        from app.domain.events import AgentRunCompleted
        await self._publish(ctx, AgentRunCompleted(
            run_id=run_id,
            output_length=len(result.output or ""),
        ))
        return new_ctx

    async def _step_save_memory(self, ctx: ConversationContext) -> ConversationContext:
        from app.application.commands.save_conversation_turn import (
            SaveConversationTurn,
        )

        if not ctx.conversation_id:
            return ctx
        if not ctx.message_original and not ctx.agent_output:
            return ctx
        await self._save_memory(
            SaveConversationTurn(
                conversation_id=ctx.conversation_id,
                user_message=ctx.message_original,
                assistant_message=ctx.agent_output or "",
                metadata={
                    "user_id": ctx.user_id,
                    "categoria": ctx.agent_route or "erro_no_orchestrator",
                    "next_action": ctx.tool_name or "orchestrator",
                    "tool_name": ctx.tool_name,
                },
            )
        )
        from app.domain.events import ConversationMemorySaved
        await self._publish(ctx, ConversationMemorySaved(
            user_turn_saved=True,
            assistant_turn_saved=True,
        ))
        # Also publish AssistantMessageRecorded for event sourcing
        from datetime import datetime
        from app.domain.projections import AssistantMessageRecorded
        await self._publish(ctx, AssistantMessageRecorded(
            content=ctx.agent_output or "",
            created_at=datetime.utcnow().isoformat(),
            metadata={
                "tool_name": ctx.tool_name,
                "route": ctx.agent_route,
            },
        ))
        return ctx


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def _record_error(ctx: ConversationContext, exc: Exception) -> ConversationContext:
    return replace(
        ctx,
        error=str(exc),
        agent_output=f"Não consegui executar o fluxo do agente. Erro: {exc}",
        agent_error=str(exc),
        tool_name="orchestrator",
    )


async def _publish_error(saga, ctx: ConversationContext, exc: Exception) -> None:
    """Publish a MessageProcessingFailed event on error."""
    from app.domain.events import MessageProcessingFailed
    if saga._events is not None:
        cid = ctx.conversation_id or "anonymous"
        event = MessageProcessingFailed(
            message_id=ctx.message_original[:50] if ctx.message_original else "",
            error_class=type(exc).__name__,
            error_message=str(exc)[:200],
            stage="saga",
        )
        fields = {k: v for k, v in event.__dict__.items() if k != "conversation_id"}
        event_with_conversation = type(event)(**fields, conversation_id=cid)
        try:
            await saga._events.publish_to_conversation(cid, event_with_conversation)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Message builders (pure functions)
# ---------------------------------------------------------------------------


def build_router_message(ctx: ConversationContext) -> str:
    """Build the message sent to the router LLM."""
    parts: list[str] = []
    if ctx.message_original:
        parts.append(f"Mensagem do usuário:\n{ctx.message_original}")
    if ctx.ocr_text:
        parts.append(f"Texto OCR tratado:\n{ctx.ocr_text}")
    if ctx.tags_encontradas:
        parts.append("Tags encontradas no OCR:\n" + "\n".join(ctx.tags_encontradas))
    if not parts:
        parts.append("Mensagem do usuário vazia ou sem texto útil.")
    return "\n\n".join(parts).strip()


def build_rag_query(ctx: ConversationContext) -> str:
    """Build the RAG search query."""
    parts: list[str] = []
    if ctx.message_original:
        parts.append(ctx.message_original)
    if ctx.ocr_text:
        parts.append(ctx.ocr_text)
    if ctx.tags_encontradas:
        parts.append("Tags: " + ", ".join(ctx.tags_encontradas))
    return "\n".join(parts) if parts else ctx.message_original


def build_agent_user_message(ctx: ConversationContext) -> str:
    """Build the final user message sent to the agent."""
    parts: list[str] = []
    if ctx.memory_context and ctx.memory_context.strip():
        parts.append(ctx.memory_context.strip())
    parts.append(build_router_message(ctx))
    base = "\n\n".join(parts).strip()
    if ctx.knowledge_context and ctx.agent_route == "pims":
        return f"{ctx.knowledge_context}\n\n---\n\nPERGUNTA DO USUÁRIO:\n{base}"
    return base
