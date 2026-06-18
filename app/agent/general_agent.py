"""
General agent — uses litellm directly to handle greetings, general chat,
and simple math expressions.

Returns a dict with the final output text and the raw message list
so the orchestrator can build an agent trace.
"""

from typing import Any

import litellm

from app.core.config import settings
from app.prompts.general_agent_prompt import GENERAL_AGENT_PROMPT
from app.schemas.llm import LLMParams


GENERAL_LLM_PARAMS = LLMParams(
    temperature=0,
    num_ctx=8192,
    num_predict=1024,
    top_p=0.1,
)


def _build_completion_kwargs() -> dict[str, Any]:
    provider = settings.LLM_PROVIDER.lower().strip()
    kwargs: dict[str, Any] = {
        "temperature": GENERAL_LLM_PARAMS.temperature,
    }

    if GENERAL_LLM_PARAMS.num_predict is not None:
        kwargs["max_tokens"] = GENERAL_LLM_PARAMS.num_predict

    if GENERAL_LLM_PARAMS.top_p is not None:
        kwargs["top_p"] = GENERAL_LLM_PARAMS.top_p

    if provider == "gemini":
        kwargs["model"] = f"gemini/{settings.GEMINI_MODEL}"
        kwargs["api_key"] = settings.GEMINI_API_KEY
    elif provider == "groq":
        kwargs["model"] = f"groq/{settings.GROQ_MODEL}"
        kwargs["api_key"] = settings.GROQ_API_KEY
    elif provider == "ollama":
        kwargs["model"] = f"ollama_chat/{settings.OLLAMA_MODEL}"
        kwargs["api_base"] = settings.OLLAMA_BASE_URL
        if GENERAL_LLM_PARAMS.format is not None:
            kwargs["format"] = GENERAL_LLM_PARAMS.format
        if GENERAL_LLM_PARAMS.keep_alive is not None:
            kwargs["keep_alive"] = str(GENERAL_LLM_PARAMS.keep_alive)
        if GENERAL_LLM_PARAMS.num_ctx is not None:
            kwargs["num_ctx"] = GENERAL_LLM_PARAMS.num_ctx
    elif provider in {"openai_compatible", "openai-compatible", "openai"}:
        kwargs["model"] = f"openai/{settings.OPENAI_COMPATIBLE_MODEL}"
        kwargs["api_key"] = settings.OPENAI_COMPATIBLE_API_KEY
        kwargs["api_base"] = settings.OPENAI_COMPATIBLE_BASE_URL
    else:
        raise ValueError(f"LLM_PROVIDER inválido: {settings.LLM_PROVIDER}")

    return kwargs


async def run_general_agent(
    user_message: str,
    memory_context: str | None = None,
) -> dict[str, Any]:
    parts: list[str] = []
    if memory_context:
        parts.append(memory_context.strip())
    parts.append(user_message.strip())

    final_user_message = "\n\n".join(p for p in parts if p)

    try:
        kwargs = _build_completion_kwargs()
        messages = [
            {"role": "system", "content": GENERAL_AGENT_PROMPT},
            {"role": "user", "content": final_user_message},
        ]

        response = await litellm.acompletion(**kwargs, messages=messages)
        content = (response.choices[0].message.content or "").strip()

        if not content:
            content = "Não consegui gerar uma resposta."

        return {
            "messages": [
                {
                    "role": "user",
                    "content": final_user_message,
                },
                {
                    "role": "assistant",
                    "content": content,
                    "name": "general_agent",
                },
            ],
            "output": content,
        }

    except Exception as e:
        return {
            "messages": [
                {
                    "role": "user",
                    "content": final_user_message,
                },
                {
                    "role": "assistant",
                    "content": (
                        "Não consegui responder agora. "
                        f"Erro ({type(e).__name__}): {e}"
                    ),
                    "name": "general_agent",
                },
            ],
            "output": (
                "Não consegui responder agora. "
                f"Erro ({type(e).__name__}): {e}"
            ),
        }
