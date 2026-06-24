"""
General agent — uses litellm directly to handle greetings, general chat,
and simple math expressions.

Returns a dict with the final output text and the raw message list
so the orchestrator can build an agent trace.
"""

from typing import Any

import litellm
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

from app.prompts.general_agent_prompt import GENERAL_AGENT_PROMPT
from app.schemas.llm import LLMParams
from app.agent.shared import build_completion_kwargs


GENERAL_LLM_PARAMS = LLMParams(
    temperature=0,
    num_ctx=8192,
    num_predict=1024,
    top_p=0.1,
)

_RETRYABLE_ERRORS = (
    ServiceUnavailableError,
    RateLimitError,
    APIConnectionError,
    Timeout,
)


async def _call_litellm(kwargs: dict[str, Any], messages: list[dict[str, str]]):
    """Call litellm.acompletion with retry on transient errors."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        reraise=True,
    ):
        with attempt:
            return await litellm.acompletion(**kwargs, messages=messages)


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
        kwargs = build_completion_kwargs(GENERAL_LLM_PARAMS)
        messages = [
            {"role": "system", "content": GENERAL_AGENT_PROMPT},
            {"role": "user", "content": final_user_message},
        ]

        response = await _call_litellm(kwargs, messages)
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
