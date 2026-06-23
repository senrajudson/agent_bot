"""Shared utilities for agent modules.

Consolidates _build_completion_kwargs which was duplicated in
router.py, general_agent.py, and ocr_query.py.
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.schemas.llm import LLMParams


def build_completion_kwargs(llm_params: LLMParams) -> dict[str, Any]:
    """Build litellm completion kwargs from LLMParams and LLM_PROVIDER.

    This is the single source of truth for LLM invocation configuration.
    Each caller provides its own LLMParams (temperature, num_predict, etc.).
    """
    provider = settings.LLM_PROVIDER.lower().strip()
    kwargs: dict[str, Any] = {}

    if llm_params.temperature is not None:
        kwargs["temperature"] = llm_params.temperature

    if llm_params.num_predict is not None:
        kwargs["max_tokens"] = llm_params.num_predict

    if llm_params.top_p is not None:
        kwargs["top_p"] = llm_params.top_p

    if provider == "gemini":
        kwargs["model"] = f"gemini/{settings.GEMINI_MODEL}"
        kwargs["api_key"] = settings.GEMINI_API_KEY
    elif provider == "groq":
        kwargs["model"] = f"groq/{settings.GROQ_MODEL}"
        kwargs["api_key"] = settings.GROQ_API_KEY
    elif provider == "ollama":
        kwargs["model"] = f"ollama_chat/{settings.OLLAMA_MODEL}"
        kwargs["api_base"] = settings.OLLAMA_BASE_URL
        if llm_params.format is not None:
            kwargs["format"] = llm_params.format
        if llm_params.think is not None:
            kwargs["think"] = llm_params.think
        if llm_params.num_ctx is not None:
            kwargs["num_ctx"] = llm_params.num_ctx
        if llm_params.keep_alive is not None:
            kwargs["keep_alive"] = str(llm_params.keep_alive)
    elif provider in {"openai_compatible", "openai-compatible", "openai"}:
        kwargs["model"] = f"openai/{settings.OPENAI_COMPATIBLE_MODEL}"
        kwargs["api_key"] = settings.OPENAI_COMPATIBLE_API_KEY
        kwargs["api_base"] = settings.OPENAI_COMPATIBLE_BASE_URL
    else:
        raise ValueError(f"LLM_PROVIDER desconhecido: {provider}")

    return kwargs
