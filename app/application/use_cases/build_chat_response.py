"""Build ChatResponse from ConversationContext (pure function)."""
from __future__ import annotations

from typing import Any

from app.application.sagas.conversation_saga import ConversationContext
from app.schemas.chat import ChatAttachment, ChatResponse

# ---------------------------------------------------------------------------
# Helpers duplicated from app/agent/orchestrator.py
# (avoiding dependency application → agent).
# ---------------------------------------------------------------------------

_TRACE_CONTENT_MAX_CHARS: int = 1000


def _content_to_text_local(content: Any) -> str:
    """Normalize message content to a plain string.

    Handles str, objects with ``.parts``, lists of dicts/objects, and
    falls back to ``str(content)``.
    """
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


def _build_trace_local(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build agent trace list from a messages list.

    Each entry contains ``type`` (role), ``name``, ``content`` (truncated),
    and ``tool_calls``.
    """
    trace: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text_parts.append(str(part.get("text", "")))
                else:
                    text_parts.append(str(part))
            content = "\n".join(text_parts)
        trace.append({
            "type": msg.get("role", "unknown"),
            "name": msg.get("name"),
            "content": str(content)[:_TRACE_CONTENT_MAX_CHARS],
            "tool_calls": msg.get("tool_calls", []),
        })
    return trace


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def build_chat_response(ctx: ConversationContext) -> ChatResponse:
    """Build a ChatResponse from the final ConversationContext.

    This is a pure function: no I/O, no side effects, no closures.
    All data is read from *ctx*.

    The three branches (error / agent_route / general) mirror the original
    inline block in ``orchestrator.process_message``.
    """
    if ctx.error:
        categoria = "erro_no_orchestrator"
        next_action = "orchestrator"
        tool_result: dict[str, Any] | None = {"error": ctx.error}
        agent_trace: list[dict[str, Any]] = []
    elif ctx.agent_route:
        categoria = ctx.agent_route
        next_action = ctx.tool_name or "orchestrator"
        agent_trace = _build_trace_local(ctx.agent_messages)
        tool_result = (
            {"agent_used": True, "agent_trace": agent_trace}
            if ctx.tool_name
            else None
        )
    else:
        categoria = "conversa_comum"
        next_action = "general_agent"
        agent_trace = _build_trace_local(ctx.agent_messages)
        tool_result = (
            {"agent_used": True, "agent_trace": agent_trace}
            if ctx.tool_name
            else None
        )

    raw_attachments = ctx.attachments or []
    valid_attachments: list[ChatAttachment] = []
    seen: set[str] = set()
    for item in raw_attachments:
        if not isinstance(item, dict):
            continue
        aid = item.get("artifact_id")
        if not isinstance(aid, str) or not aid.strip():
            continue
        if aid in seen:
            continue
        seen.add(aid)
        try:
            valid_attachments.append(ChatAttachment(**item))
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("attachment_invalid artifact_id=%s", aid)
    if len(valid_attachments) > 3:
        valid_attachments = valid_attachments[:3]
    total_bytes = sum(a.size_bytes or 0 for a in valid_attachments)
    if total_bytes > 52428800:
        valid_attachments = []

    return ChatResponse(
        ok=ctx.error is None,
        user_id=ctx.user_id,
        message_original=ctx.message_original,
        processed_message=ctx.message_original,
        categoria=categoria,
        next_action=next_action,
        has_image=bool(ctx.images),
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
        attachments=valid_attachments,
    )
