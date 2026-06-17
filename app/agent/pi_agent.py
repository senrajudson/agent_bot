"""
PI System agent — Google ADK based.

Uses ADK's LlmAgent + McpToolset (Streamable HTTP) to talk to the
standalone MCP server (mcp_server/) and execute tag queries,
historical statistics, calculus and status checks.
"""

from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from google.genai import types as genai_types

from app.clients.provider_client import get_llm
from app.core.config import settings
from app.prompts.pi_agent_prompt import AGENT_SYSTEM_PROMPT
from app.schemas.llm import LLMParams


APP_NAME = "agent_bot_pi"
PI_AGENT_NAME = "pi_agent"
MAX_AGENT_STEPS = 8


def _mcp_toolset() -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=settings.MCP_SERVER_URL,
        ),
    )


def _build_pi_agent() -> LlmAgent:
    model = get_llm(
        LLMParams(
            temperature=0,
            num_predict=1024,
            top_p=0.1,
        )
    )
    return LlmAgent(
        name=PI_AGENT_NAME,
        model=model,
        instruction=AGENT_SYSTEM_PROMPT,
        tools=[_mcp_toolset()],
    )


def _safe_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content

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
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()

    return str(content)


def _event_to_message(event: Any) -> dict[str, Any] | None:
    content = getattr(event, "content", None)
    if content is None:
        return None

    author = getattr(event, "author", None) or "pi_agent"
    text = _safe_text(content)

    function_calls: list[dict[str, Any]] = []
    function_responses: list[dict[str, Any]] = []

    parts = getattr(content, "parts", None) or []
    for part in parts:
        if getattr(part, "function_call", None):
            fc = part.function_call
            function_calls.append(
                {
                    "name": getattr(fc, "name", None),
                    "args": dict(getattr(fc, "args", {}) or {}),
                }
            )
        if getattr(part, "function_response", None):
            fr = part.function_response
            function_responses.append(
                {
                    "name": getattr(fr, "name", None),
                    "response": getattr(fr, "response", None),
                }
            )

    if not text and not function_calls and not function_responses:
        return None

    msg: dict[str, Any] = {
        "role": "assistant" if not function_calls else "tool_call",
        "name": author,
        "content": text,
    }
    if function_calls:
        msg["tool_calls"] = function_calls
    if function_responses:
        msg["tool_responses"] = function_responses
    return msg


def _classify_error(error: Exception) -> str:
    error_type = type(error).__name__
    error_msg = str(error) or error_type

    if "RecursionError" in error_type or "recursion_limit" in error_msg.lower():
        return (
            "Não consegui concluir a consulta porque o agente "
            "excedeu o número máximo de etapas permitidas. "
            "Tente reformular a pergunta com mais detalhes."
        )

    if "RateLimitError" in error_type or "rate_limit" in error_msg.lower() or "429" in error_msg:
        return "Serviço temporariamente sobrecarregado. Tente novamente em instantes."

    if "AuthenticationError" in error_type or "401" in error_msg:
        return "Chave de API do modelo LLM inválida ou expirada. Verifique a configuração."

    if "ClosedResourceError" in error_type or "Mcp" in error_type:
        return "Conexão com o servidor de ferramentas (MCP) foi fechada. Tente novamente."

    return f"Não consegui executar a consulta. Erro ({error_type}): {error_msg}"


def _detect_repeated_tool_calls(messages: list[dict[str, Any]]) -> bool:
    counts: dict[str, int] = {}
    for msg in messages:
        for tc in msg.get("tool_calls") or []:
            name = tc.get("name") or ""
            args = tc.get("args") or {}
            key = f"{name}:{sorted(args.items())}"
            counts[key] = counts.get(key, 0) + 1
            if counts[key] >= 3:
                return True
    return False


async def run_pi_agent(
    user_message: str,
    user_id: str = "default_user",
    session_id: str | None = None,
) -> dict[str, Any]:
    session_id = session_id or f"pi-{user_id}"

    try:
        session_service = InMemorySessionService()
        runner = Runner(
            agent=_build_pi_agent(),
            app_name=APP_NAME,
            session_service=session_service,
        )

        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_message)],
        )

        messages: list[dict[str, Any]] = []
        final_output: str | None = None

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if getattr(event, "error_message", None):
                return {
                    "messages": messages,
                    "output": _classify_error(Exception(event.error_message)),
                    "error": event.error_message,
                }

            msg = _event_to_message(event)
            if msg:
                messages.append(msg)

            if getattr(event, "is_final_response", lambda: False)():
                if msg and msg.get("content"):
                    final_output = msg["content"]
                elif getattr(event, "actions", None):
                    final_output = final_output or ""

        if _detect_repeated_tool_calls(messages):
            return {
                "messages": messages,
                "output": (
                    "Não consegui concluir a consulta porque o agente "
                    "tentou repetir a mesma chamada de ferramenta múltiplas vezes. "
                    "A execução foi encerrada para evitar repetição."
                ),
                "error": "tool_call_repeated",
            }

        if not final_output:
            final_output = "Não consegui gerar uma resposta final."

        return {
            "messages": messages,
            "output": final_output,
            "error": None,
        }

    except Exception as e:
        return {
            "messages": [],
            "output": _classify_error(e),
            "error": str(e),
        }
