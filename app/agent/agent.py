"""
Generic LLM agent — Google ADK based.

Uses ADK's LlmAgent + McpToolset (Streamable HTTP) to talk to the
standalone MCP server (mcp_server/) and execute tag queries,
historical statistics, calculus and status checks.
"""

import json
import logging
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from google.genai import types as genai_types
from litellm.exceptions import (
    APIConnectionError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.clients.provider_client import get_llm, get_llm_for_model
from app.core.config import settings
from app.prompts.agent_prompt import build_system_prompt
from app.schemas.llm import LLMParams
from app.agent.shared import RETRYABLE_ERRORS

logger = logging.getLogger(__name__)

APP_NAME = "agent_bot"
AGENT_NAME = "agent"
MAX_AGENT_STEPS = 8

_AGENT_PARAMS = LLMParams(
    temperature=0,
    num_ctx=8192,
    num_predict=1024,
    top_p=0.1,
)


def _mcp_toolset() -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=settings.MCP_SERVER_URL,
        ),
    )


def _build_agent(model_name: str | None = None) -> LlmAgent:
    """Build agent with a specific Gemini model (or default if None)."""
    if model_name:
        model = get_llm_for_model(_AGENT_PARAMS, model_name)
    else:
        model = get_llm(_AGENT_PARAMS)

    return LlmAgent(
        name=AGENT_NAME,
        model=model,
        instruction=build_system_prompt(
            enable_test_artifact_tool=settings.ENABLE_TEST_ARTIFACT_TOOL,
        ),
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

    author = getattr(event, "author", None) or "agent"
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

    if (
        "ServiceUnavailableError" in error_type
        or "APIConnectionError" in error_type
        or "Timeout" in error_type
        or "503" in error_msg
    ):
        return (
            "O serviço de IA está temporariamente indisponível. "
            "Tente novamente em instantes."
        )

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


_ENVELOPE_TYPE = "agent_artifact_result"

_ALLOWED_ATTACHMENT_MIMES = {
    "text/plain",
    "text/csv",
    "application/pdf",
    "image/png",
    "image/jpeg",
}


def _dedupe_by_artifact_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        aid = item.get("artifact_id")
        if aid and aid not in seen:
            seen.add(aid)
            result.append(item)
    return result


def _enforce_attachment_limits(
    items: list[dict[str, Any]],
    max_count: int = 3,
    max_total_bytes: int = 52428800,
) -> list[dict[str, Any]]:
    truncated = items[:max_count]
    total = sum(
        item.get("size_bytes") or 0 for item in truncated
    )
    if total > max_total_bytes:
        logger.warning(
            "attachment_limit: total_bytes=%d exceeds %d — discarding all",
            total, max_total_bytes,
        )
        return []
    return truncated


def _is_valid_attachment(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    aid = item.get("artifact_id")
    fn = item.get("filename")
    mt = item.get("mime_type")
    if not (isinstance(aid, str) and aid.strip()):
        return False
    if not (isinstance(fn, str) and fn.strip()):
        return False
    if not (isinstance(mt, str) and mt.strip()):
        return False
    cas = item.get("cleanup_after_send", False)
    if not isinstance(cas, bool):
        return False
    cap = item.get("caption")
    if cap is not None and not isinstance(cap, str):
        return False
    sb = item.get("size_bytes")
    if sb is not None and not (isinstance(sb, int) and sb >= 0):
        return False
    if mt not in _ALLOWED_ATTACHMENT_MIMES:
        logger.warning(
            "attachment_invalid_mime: mime_type=%s artifact_id=%s",
            mt, aid,
        )
        return False
    if any(k in item for k in ("path", "download_url", "internal_url")):
        logger.warning(
            "attachment_rejected_path: artifact_id=%s keys=%s",
            aid, [k for k in item if k in ("path", "download_url", "internal_url")],
        )
        return False
    return True


def _extract_attachments_from_agent_output(
    output: str,
    agent_messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Parse 'agent_artifact_result' envelope from MCP tool output.

    Strategy:
      1. Try ``json.loads(output)``.
         If ``type == "agent_artifact_result"`` and ``attachments`` is a list,
         validate each item, dedupe, enforce limits, and return.
      2. If step 1 fails, scan ``agent_messages[*]["tool_responses"][*]``
         for an envelope. ``response`` may be a dict (real ADK output) or
         a JSON string (legacy). Covers the real ADK path where the LLM
         emits a clean final text (per system prompt) and the envelope
         lives in the tool response payload.
      3. If step 2 fails, scan ``agent_messages`` for tool role messages
         whose content matches the envelope (legacy format).
      4. Fallback: ``(output, [])``.
    """
    import json as _json

    def _process_attachments(raw: list[Any]) -> list[dict[str, Any]]:
        valid = [a for a in raw if _is_valid_attachment(a)]
        valid = _dedupe_by_artifact_id(valid)
        valid = _enforce_attachment_limits(valid)
        return valid

    def _envelope_from_payload(payload: Any) -> tuple[str, list[dict[str, Any]]] | None:
        if isinstance(payload, str):
            try:
                payload = _json.loads(payload)
            except (ValueError, TypeError):
                return None
        if (
            isinstance(payload, dict)
            and payload.get("type") == _ENVELOPE_TYPE
            and isinstance(payload.get("attachments"), list)
        ):
            valid = _process_attachments(payload["attachments"])
            return (payload.get("answer", output), valid)
        return None

    def _unpack_mcp_tool_response(payload: Any) -> Any:
        """Unpack google-adk 2.2.0 MCP CallToolResult.model_dump() wrapper.

        The ADK delivers tool responses as the model_dump of CallToolResult::

            {
              "content": [{"type": "text", "text": "<envelope_json_string>"}],
              "structuredContent": <dict> | None
            }

        FastMCP, when a tool has a primitive return type (e.g. ``str``), wraps
        the result via ``wrap_output=True`` and produces::

            {"structuredContent": {"result": "<original_string>"}}

        instead of the envelope dict directly. This helper unwraps that case
        so ``_envelope_from_payload`` can parse the underlying string.

        Returns the envelope payload (dict for structuredContent, str for
        TextContent or unwrapped wrap_output), or None if the payload doesn't
        match the wrapper.
        """
        if not isinstance(payload, dict):
            return None
        # Prefer structuredContent (declared output schema)
        sc = payload.get("structuredContent")
        if isinstance(sc, dict):
            # FastMCP wrap_output=True for primitive return types: the dict is
            # {"result": "<original_string>"} and the envelope lives inside.
            # If sc is not itself the envelope, unwrap the "result" key.
            if sc.get("type") != _ENVELOPE_TYPE:
                inner = sc.get("result")
                if isinstance(inner, str) and inner:
                    return inner
            return sc
        # Fall back to content[0].text (TextContent)
        content = payload.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text = first.get("text")
                if isinstance(text, str):
                    return text
        return None

    # Step 1: try the final output string
    if output:
        result = _envelope_from_payload(output)
        if result is not None:
            return result

    # Step 2: scan agent_messages[*]["tool_responses"][*]
    for msg in agent_messages:
        tool_responses = msg.get("tool_responses") or []
        if not isinstance(tool_responses, list):
            continue
        for tr in tool_responses:
            if not isinstance(tr, dict):
                continue
            response = tr.get("response")
            # 2a: try direct dict/string (legacy synthetic tests)
            result = _envelope_from_payload(response)
            if result is not None:
                return result
            # 2b: try google-adk 2.2.0 MCP wrapper (real ADK path)
            unpacked = _unpack_mcp_tool_response(response)
            if unpacked is not None:
                result = _envelope_from_payload(unpacked)
                if result is not None:
                    return result
            # 2c: defense in depth — try content[0].text directly from
            # the wrapper (covers cases where structuredContent is
            # absent or unhelpful but the envelope lives in TextContent).
            if isinstance(response, dict):
                content = response.get("content")
                if isinstance(content, list) and content:
                    first = content[0]
                    if isinstance(first, dict) and first.get("type") == "text":
                        text = first.get("text")
                        if isinstance(text, str):
                            result = _envelope_from_payload(text)
                            if result is not None:
                                return result

    # Step 3: scan agent_messages for tool role with content string (legacy)
    for msg in agent_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "tool" and isinstance(content, str):
            result = _envelope_from_payload(content)
            if result is not None:
                return result

    return (output, [])


# ---------------------------------------------------------------------------
# Search loop policy — max 2 calls of search_pi_points per turn
#
# Decision point analysis (T1):
# _detect_repeated_tool_calls runs AFTER runner.run_async completes, so it
# does NOT prevent tool calls from executing. The same applies here: we
# post-process messages after the ADK loop, overriding the final output
# when the policy is violated. This is consistent with the existing
# architecture and sufficient because the MCP tool is lightweight and
# stateless. The override ensures the user receives a clean answer.
# ---------------------------------------------------------------------------

_MAX_SEARCH_PI_POINTS_CALLS_PER_TURN = 2
_SEARCH_TOOL_NAME = "search_pi_points"
_JACCARD_THRESHOLD = 0.5

_ACCENT_MAP = str.maketrans({
    "á": "a", "à": "a", "ã": "a", "â": "a",
    "é": "e", "ê": "e", "è": "e",
    "í": "i", "ì": "i", "î": "i",
    "ó": "o", "ò": "o", "õ": "o", "ô": "o",
    "ú": "u", "ù": "u", "û": "u",
    "ç": "c",
    "ü": "u",
})

_STOPWORDS_SEARCH: set[str] = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
    "por", "para", "pelo", "pela", "com", "sem", "sob", "sobre",
    "e", "ou", "mas", "que", "se", "é", "foi", "ser", "estar",
    "tem", "ter", "há", "haver", "existe", "existem",
    "algum", "alguma", "alguns", "algumas", "todo", "toda", "todos", "todas",
    "muito", "muita", "pouco", "pouca", "mais", "menos", "qual", "quais",
    "como", "aqui", "ali", "lá", "onde", "quando", "porque",
    "eu", "tu", "ele", "ela", "nós", "vós", "eles", "elas",
    "meu", "minha", "teu", "tua", "seu", "sua", "nosso", "nossa",
    "este", "esta", "isto", "esse", "essa", "isso", "aquele", "aquela", "aquilo",
    "tal", "tais", "certo", "certa", "apenas", "só", "somente",
    "tag", "tags",
    "procure", "procura", "procurar", "buscar", "localizar", "encontrar",
    "lista", "listar", "mostra", "mostrar", "retorna", "retornar",
    "me", "te", "se", "lhe", "nos", "vos",
    "pode", "poderia", "poder", "gostaria", "queria", "quero",
    "sobre", "ainda", "já", "também", "bem", "sempre",
    "relacionada", "relacionado", "referente",
}

_SEARCH_FINAL_RESPONSE_BLOCKED = (
    "Você já atingiu o limite de 2 buscas de tags neste turno. "
    "Pare de chamar ferramentas de busca e responda ao usuário com o "
    "melhor resultado já obtido. Se não houver correspondência forte, "
    "peça mais detalhes como área, equipamento ou parte do nome."
)

_SEARCH_FINAL_RESPONSE_NO_CANDIDATES = (
    "Você já realizou 2 buscas de tags sem encontrar candidatos "
    "adequados. Informe ao usuário que não foi possível localizar "
    "a tag e peça mais detalhes como área, equipamento ou parte do nome."
)


# -- T3: Query normalization and Jaccard similarity


def _normalize_query_tokens(query: str) -> set[str]:
    if not query:
        return set()
    lower = query.lower().translate(_ACCENT_MAP)
    tokens: set[str] = set()
    for raw in lower.split():
        t = raw.strip(".,;:!?\"'()[]{}")
        if not t or len(t) < 2:
            continue
        if t in _STOPWORDS_SEARCH:
            continue
        tokens.add(t)
    return tokens


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# -- T4: Materially different query check


def _queries_materialmente_diferentes(q1: str, q2: str) -> bool:
    t1 = _normalize_query_tokens(q1)
    t2 = _normalize_query_tokens(q2)
    similarity = _jaccard_similarity(t1, t2)
    if similarity >= _JACCARD_THRESHOLD:
        new_tokens = t2 - t1
        for t in new_tokens:
            if len(t) >= 3:
                return True
        return False
    return True


# -- T2: Parse tool response payload (various MCP wrapping formats)


def _parse_tool_response_payload(response: Any) -> dict | None:
    if response is None:
        return None
    if isinstance(response, dict):
        inner = (
            response.get("structuredContent")
            or response.get("content")
            or response.get("result")
        )
        if isinstance(inner, dict):
            return inner
        return response
    if isinstance(response, str):
        try:
            parsed = json.loads(response)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# -- T2: Extract search_pi_points calls from messages


def _extract_search_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for msg in messages:
        for tc in msg.get("tool_calls") or []:
            if tc.get("name") == _SEARCH_TOOL_NAME:
                args = tc.get("args") or {}
                calls.append({
                    "name": _SEARCH_TOOL_NAME,
                    "args": args,
                    "query": args.get("query", ""),
                    "response": None,
                    "index": len(calls),
                })
        for tr in msg.get("tool_responses") or []:
            if tr.get("name") == _SEARCH_TOOL_NAME and calls:
                calls[-1]["response"] = tr.get("response")
    return calls


# -- T5: Weak result classifier and result ranker


def _is_weak_search_result(payload: dict | None) -> bool:
    if payload is None:
        return False
    if not payload.get("success", True):
        return True
    count = payload.get("count", 0)
    if count == 0:
        return True
    max_count = payload.get("max_count", 0)
    if max_count > 0 and count >= max_count:
        items = payload.get("items") or []
        if all(not item.get("description") for item in items):
            return True
    return False


def _rank_search_result(payload: dict | None) -> int:
    if payload is None:
        return 0
    if not payload.get("success", True):
        return 0
    count = payload.get("count", 0)
    if count == 0:
        return 1
    items = payload.get("items") or []
    if any(item.get("description") for item in items):
        return 3
    return 2


def _best_search_result(calls: list[dict[str, Any]]) -> dict | None:
    best: dict | None = None
    best_rank = -1
    for call in calls:
        payload = _parse_tool_response_payload(call.get("response"))
        call["response_payload"] = payload
        rank = _rank_search_result(payload)
        if rank > best_rank:
            best_rank = rank
            best = payload
    return best


# -- T6: Main enforcement function


def _enforce_search_loop_policy(
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    calls = _extract_search_calls(messages)
    total = len(calls)
    kept = total
    blocked = 0
    reason = "ok"
    override: str | None = None

    if total > _MAX_SEARCH_PI_POINTS_CALLS_PER_TURN:
        kept = _MAX_SEARCH_PI_POINTS_CALLS_PER_TURN
        blocked = total - kept
        reason = "third_call_blocked"
        best = _best_search_result(calls)
        if best and best.get("count", 0) > 0:
            items = best.get("items") or []
            names = [i.get("name", "?") for i in items[:5]]
            override = (
                "Você já realizou 2 buscas de tags neste turno. "
                "Com base nos resultados obtidos, "
                f"os melhores candidatos encontrados são: {', '.join(names)}. "
                "Responda ao usuário com essas informações."
            )
        else:
            override = _SEARCH_FINAL_RESPONSE_NO_CANDIDATES
    elif total == 2:
        first_payload = _parse_tool_response_payload(calls[0].get("response"))
        first_query = calls[0].get("query", "")
        second_query = calls[1].get("query", "")

        if not _is_weak_search_result(first_payload):
            kept = 1
            blocked = 1
            reason = "first_call_strong"
        elif not _queries_materialmente_diferentes(first_query, second_query):
            kept = 1
            blocked = 1
            reason = "second_call_not_different"

    logger.info(
        "search_loop_policy: kept=%d blocked=%d reason=%s",
        kept, blocked, reason,
    )
    logger.debug(
        "search_loop_policy: total=%d queries=%r reason=%s",
        total, [c.get("query", "") for c in calls], reason,
    )

    return {
        "kept": kept,
        "blocked": blocked,
        "reason": reason,
        "final_response_override": override,
    }


async def _run_agent_core(
    user_message: str,
    user_id: str,
    session_id: str,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Core agent logic with a specific model."""
    agent = _build_agent(model_name=model_name)
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
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
                "attachments": [],
            }

        msg = _event_to_message(event)
        if msg:
            messages.append(msg)

        if getattr(event, "is_final_response", lambda: False)():
            if msg and msg.get("content"):
                final_output = msg["content"]
            elif getattr(event, "actions", None):
                final_output = final_output or ""

    # Enforce search loop policy (max 2 search_pi_points per turn)
    search_decision = _enforce_search_loop_policy(messages)
    if search_decision["final_response_override"] is not None:
        return {
            "messages": messages,
            "output": search_decision["final_response_override"],
            "error": "search_loop_blocked",
            "attachments": [],
        }

    # Secondary safety net: exact repeat of same tool+args (3+ times)
    if _detect_repeated_tool_calls(messages):
        return {
            "messages": messages,
            "output": (
                "Não consegui concluir a consulta porque o agente "
                "tentou repetir a mesma chamada de ferramenta múltiplas vezes. "
                "A execução foi encerrada para evitar repetição."
            ),
            "error": "tool_call_repeated",
            "attachments": [],
        }

    if not final_output:
        final_output = "Não consegui gerar uma resposta final."

    attachments_result = _extract_attachments_from_agent_output(final_output, messages)
    clean_output = attachments_result[0]
    attachments = attachments_result[1]

    return {
        "messages": messages,
        "output": clean_output,
        "error": None,
        "attachments": attachments,
    }


async def run_agent(
    user_message: str,
    user_id: str = "default_user",
    session_id: str | None = None,
) -> dict[str, Any]:
    session_id = session_id or f"agent-{user_id}"

    provider = settings.LLM_PROVIDER.lower().strip()
    models: list[str | None] = [None]  # None = use default get_llm

    if provider == "gemini":
        models = [settings.GEMINI_MODEL]
        if settings.GEMINI_FALLBACK_MODEL:
            models.append(settings.GEMINI_FALLBACK_MODEL)

    last_exc: Exception | None = None
    for model_name in models:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(RETRYABLE_ERRORS),
                reraise=True,
            ):
                with attempt:
                    return await _run_agent_core(
                        user_message, user_id, session_id, model_name=model_name
                    )
        except RETRYABLE_ERRORS as e:
            logger.warning(
                "agent model %s failed after retries: %s. Trying next model.",
                model_name,
                e,
            )
            last_exc = e
            continue
        except Exception:
            raise

    # All models exhausted
    if last_exc:
        return {
            "messages": [],
            "output": _classify_error(last_exc),
            "error": str(last_exc),
            "attachments": [],
        }
    # Should not reach here, but just in case
    return {
        "messages": [],
        "output": "Erro desconhecido no agent.",
        "error": "unknown",
        "attachments": [],
    }
