from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agent.router import route_message
from app.agent.general_agent import run_general_agent
# from app.agent.calculator_agent import run_calculator_agent
from app.agent.pi_agent import run_pi_agent
from app.clients.provider_client import get_llm
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.llm import LLMParams, AGENT_DEFAULT
from app.services.chat_memory_service import (
    append_memory_turns,
    format_memory_for_prompt,
    load_memory_turns,
)
from app.tasks.ocr_query import run_ocr_for_images


DEFAULT_TIMEZONE = "America/Sao_Paulo"


ROUTER_LLM_PARAMS = LLMParams(
    **AGENT_DEFAULT,
    num_predict=512,
)

CONVERSA_COMUM_LLM_PARAMS = LLMParams(
    **AGENT_DEFAULT,
    num_predict=1024,
)

PIMS_LLM_PARAMS = LLMParams(
    **AGENT_DEFAULT,
    num_predict=1024,
)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")

                if text:
                    parts.append(str(text))
            else:
                parts.append(str(item))

        return "\n".join(parts).strip()

    return str(content).strip()


def extract_final_text(agent_result: dict[str, Any]) -> str:
    messages = agent_result.get("messages", [])

    if not messages:
        return "Não consegui gerar uma resposta final."

    last_message = messages[-1]
    content = getattr(last_message, "content", "")

    final_text = _content_to_text(content)

    if not final_text:
        return "Não consegui gerar uma resposta final."

    return final_text


def build_safe_agent_trace(agent_result: dict[str, Any]) -> list[dict[str, Any]]:
    messages = agent_result.get("messages", [])
    trace = []

    for message in messages:
        content = getattr(message, "content", "")
        tool_calls = getattr(message, "tool_calls", None)

        trace.append(
            {
                "type": getattr(message, "type", message.__class__.__name__),
                "name": getattr(message, "name", None),
                "content": _content_to_text(content)[:1000],
                "tool_calls": tool_calls or [],
            }
        )

    return trace


async def _ocr_step(state: dict) -> dict:
    images = state.get("images") or []

    if not images:
        state["skip_ocr"] = True
        state["ocr_results"] = []
        state["ocr_text"] = None
        state["tags_encontradas"] = []
        return state

    ocr_results = await run_ocr_for_images(images)

    ocr_text_parts = []
    tags_encontradas = []

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
    conversation_id = state.get("conversation_id")

    turns = await load_memory_turns(
        conversation_id=conversation_id,
    )

    state["memory_turns"] = turns
    state["memory_context"] = format_memory_for_prompt(turns) or None

    return state


async def _save_memory(state: dict) -> dict:
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


def build_router_message(state: dict) -> str:
    user_message = (state.get("message_original") or "").strip()
    ocr_text = (state.get("ocr_text") or "").strip()
    tags = state.get("tags_encontradas") or []

    parts = []

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
    memory_context = (state.get("memory_context") or "").strip()
    message = build_router_message(state)
    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat(timespec="seconds")

    parts = []

    if memory_context:
        parts.append(memory_context)

    parts.append(message)

    parts.append(
        "Referência temporal atual:\n"
        f"Data/hora: {now}\n"
        f"Timezone: {DEFAULT_TIMEZONE}"
    )

    return "\n\n".join(parts).strip()


async def _run_general_route(
    llm_agent,
    user_message: str,
    state: dict,
) -> dict:
    result = await run_general_agent(
        llm=llm_agent,
        user_message=user_message,
    )

    agent_trace = build_safe_agent_trace(result)

    state["categoria"] = "conversa_comum"
    state["next_action"] = "general_agent"
    state["tool_name"] = "general_agent"
    state["tool_result"] = {
        "agent_used": True,
        "agent_trace": agent_trace,
    }
    state["agent_trace"] = agent_trace
    state["output"] = extract_final_text(result)
    state["answer_generation_error"] = None

    return state


async def _run_pims_route(
    llm_agent,
    user_message: str,
    state: dict,
) -> dict:
    result = await run_pi_agent(
        llm=llm_agent,
        user_message=user_message,
    )

    agent_trace = build_safe_agent_trace(result)

    state["categoria"] = "pims"
    state["next_action"] = "pi_agent"
    state["tool_name"] = "pi_agent"
    state["tool_result"] = {
        "agent_used": True,
        "agent_trace": agent_trace,
    }
    state["agent_trace"] = agent_trace
    state["output"] = extract_final_text(result)
    state["answer_generation_error"] = None

    return state


async def _run_selected_agent(
    route_name: str,
    user_message: str,
    state: dict,
) -> dict:
    llm_conversa_comum = get_llm(CONVERSA_COMUM_LLM_PARAMS)
    llm_pims = get_llm(PIMS_LLM_PARAMS)

    if route_name == "conversa_comum":
        return await _run_general_route(
            llm_agent=llm_conversa_comum,
            user_message=user_message,
            state=state,
        )

    if route_name == "pims":
        return await _run_pims_route(
            llm_agent=llm_pims,
            user_message=user_message,
            state=state,
        )

    return await _run_general_route(
        llm_agent=llm_conversa_comum,
        user_message=user_message,
        state=state,
    )


async def run_agent(state: dict) -> dict:
    state = await _load_memory(state)
    state = await _ocr_step(state)

    router_message = build_router_message(state)
    agent_user_message = build_agent_user_message(state)

    try:
        llm_router = get_llm(ROUTER_LLM_PARAMS)

        route = await route_message(
            llm=llm_router,
            user_message=router_message,
        )

        state["router_result"] = route.model_dump()

        state = await _run_selected_agent(
            route_name=route.rota,
            user_message=agent_user_message,
            state=state,
        )

        return await _save_memory(state)

    except Exception as error:
        state["categoria"] = "erro_no_orchestrator"
        state["next_action"] = "orchestrator"
        state["tool_name"] = "orchestrator"
        state["tool_result"] = {
            "error": str(error),
        }
        state["agent_trace"] = []
        state["output"] = (
            "Não consegui executar o fluxo do agente. "
            f"Erro: {error}"
        )
        state["answer_generation_error"] = str(error)

        return await _save_memory(state)


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


async def process_message(payload: ChatRequest) -> ChatResponse:
    message_original = _get_payload_message(payload)
    images = _get_payload_images(payload)
    user_id = _get_payload_user_id(payload)
    conversation_id = _get_payload_conversation_id(payload)

    state = {
        "user_id": user_id,
        "conversation_id": conversation_id,

        "message_original": message_original,
        "processed_message": message_original,

        "images": images,
        "has_image": bool(images),

        "memory_turns": [],
        "memory_context": None,

        "skip_ocr": True,
        "ocr_results": [],
        "ocr_text": None,
        "tags_encontradas": [],
        "tags_consultadas": [],

        "categoria": None,
        "next_action": None,

        "tool_name": None,
        "tool_result": None,
        "agent_trace": [],

        "output": None,
        "answer_generation_error": None,
    }

    state = await run_agent(state)

    return ChatResponse(
        ok=state.get("answer_generation_error") is None,

        user_id=state.get("user_id"),
        conversation_id=state.get("conversation_id"),

        message_original=message_original,
        processed_message=state.get("processed_message"),

        categoria=state.get("categoria"),
        next_action=state.get("next_action"),

        has_image=state.get("has_image", False),
        skip_ocr=state.get("skip_ocr", True),

        ocr_text=state.get("ocr_text"),
        tags_encontradas=state.get("tags_encontradas", []),
        tags_consultadas=state.get("tags_consultadas", []),
        ocr_results=state.get("ocr_results", []),

        tool_name=state.get("tool_name"),
        tool_result=state.get("tool_result"),
        agent_trace=state.get("agent_trace", []),

        output=state.get("output"),
        answer_generation_error=state.get("answer_generation_error"),
    )