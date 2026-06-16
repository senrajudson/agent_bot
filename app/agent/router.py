"""
Route classifier — uses litellm directly to classify the user message
into one of the available routes.

Routes:
- conversa_comum: greetings, general chat, simple math
- pims: tag queries, historical stats, calculus, PIMS status
- calculadora: pure math expressions
"""

import json
import re
from typing import Literal

import litellm
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.prompts.router_prompt import ROUTER_PROMPT
from app.schemas.llm import LLMParams


RouteName = Literal[
    "conversa_comum",
    "calculadora",
    "pims",
]


class RouterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rota: RouteName = Field(
        description=(
            "Rota escolhida para tratar a mensagem do usuário. "
            "Use somente: conversa_comum, calculadora ou pims."
        )
    )


VALID_ROUTES = {"conversa_comum", "calculadora", "pims"}

ROUTER_LLM_PARAMS = LLMParams(
    temperature=0,
    num_predict=64,
    top_p=0.1,
)


def _fallback_route() -> RouterOutput:
    return RouterOutput(rota="conversa_comum")


def _build_completion_kwargs() -> dict:
    provider = settings.LLM_PROVIDER.lower().strip()
    kwargs: dict = {
        "temperature": ROUTER_LLM_PARAMS.temperature,
    }

    if ROUTER_LLM_PARAMS.num_predict is not None:
        kwargs["max_tokens"] = ROUTER_LLM_PARAMS.num_predict

    if ROUTER_LLM_PARAMS.top_p is not None:
        kwargs["top_p"] = ROUTER_LLM_PARAMS.top_p

    if provider == "gemini":
        kwargs["model"] = f"gemini/{settings.GEMINI_MODEL}"
        kwargs["api_key"] = settings.GEMINI_API_KEY
    elif provider == "groq":
        kwargs["model"] = f"groq/{settings.GROQ_MODEL}"
        kwargs["api_key"] = settings.GROQ_API_KEY
    elif provider == "ollama":
        kwargs["model"] = f"ollama_chat/{settings.OLLAMA_MODEL}"
        kwargs["api_base"] = settings.OLLAMA_BASE_URL
        if ROUTER_LLM_PARAMS.format is not None:
            kwargs["format"] = ROUTER_LLM_PARAMS.format
    elif provider in {"openai_compatible", "openai-compatible", "openai"}:
        kwargs["model"] = f"openai/{settings.OPENAI_COMPATIBLE_MODEL}"
        kwargs["api_key"] = settings.OPENAI_COMPATIBLE_API_KEY
        kwargs["api_base"] = settings.OPENAI_COMPATIBLE_BASE_URL
    else:
        raise ValueError(f"LLM_PROVIDER inválido: {settings.LLM_PROVIDER}")

    return kwargs


def _parse_route_from_text(text: str) -> RouterOutput:
    if not text:
        return _fallback_route()

    try:
        data = json.loads(text)
    except Exception:
        match = re.search(r'"rota"\s*:\s*"([a-z_]+)"', text)
        if match:
            candidate = match.group(1).strip()
            if candidate in VALID_ROUTES:
                return RouterOutput(rota=candidate)
        return _fallback_route()

    if not isinstance(data, dict):
        return _fallback_route()

    candidate = data.get("rota")
    if isinstance(candidate, str) and candidate in VALID_ROUTES:
        return RouterOutput(rota=candidate)

    return _fallback_route()


async def route_message(user_message: str) -> RouterOutput:
    if not user_message or not user_message.strip():
        return _fallback_route()

    try:
        kwargs = _build_completion_kwargs()

        messages = [
            {"role": "system", "content": ROUTER_PROMPT},
            {
                "role": "user",
                "content": (
                    "Classifique a mensagem a seguir e responda APENAS com o JSON "
                    "solicitado, sem texto adicional.\n\n"
                    f"Mensagem:\n{user_message}"
                ),
            },
        ]

        response = await litellm.acompletion(
            **kwargs,
            messages=messages,
        )

        text = (response.choices[0].message.content or "").strip()
        return _parse_route_from_text(text)

    except Exception:
        return _fallback_route()
