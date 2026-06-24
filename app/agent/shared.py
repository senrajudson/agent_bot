"""Shared utilities for agent modules.

Consolidates _build_completion_kwargs which was duplicated in
router.py, general_agent.py, and ocr_query.py.
"""
from __future__ import annotations

import logging
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

from app.core.config import settings
from app.schemas.llm import LLMParams

logger = logging.getLogger(__name__)

RETRYABLE_ERRORS = (
    ServiceUnavailableError,
    RateLimitError,
    APIConnectionError,
    Timeout,
)


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


def _gemini_kwargs_for_model(
    llm_params: LLMParams,
    model_name: str,
) -> dict[str, Any]:
    """Build litellm kwargs for a specific Gemini model."""
    kwargs: dict[str, Any] = {"model": f"gemini/{model_name}"}

    if settings.GEMINI_API_KEY:
        kwargs["api_key"] = settings.GEMINI_API_KEY

    if llm_params.temperature is not None:
        kwargs["temperature"] = llm_params.temperature
    if llm_params.num_predict is not None:
        kwargs["max_tokens"] = llm_params.num_predict
    if llm_params.top_p is not None:
        kwargs["top_p"] = llm_params.top_p

    return kwargs


async def call_with_model_fallback(
    llm_params: LLMParams,
    messages: list[dict[str, str]],
    max_attempts_per_model: int = 3,
):
    """Call litellm with retry on each model; fall back to GEMINI_FALLBACK_MODEL.

    Tries GEMINI_MODEL first (with tenacity retry). If that fails with a
    retryable error after max_attempts_per_model, tries GEMINI_FALLBACK_MODEL
    (also with retry). Raises the last exception if all models exhaust.
    """
    models = [settings.GEMINI_MODEL]
    if settings.GEMINI_FALLBACK_MODEL:
        models.append(settings.GEMINI_FALLBACK_MODEL)

    last_exc: Exception | None = None
    for model in models:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts_per_model),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(RETRYABLE_ERRORS),
                reraise=True,
            ):
                with attempt:
                    return await litellm.acompletion(
                        **_gemini_kwargs_for_model(llm_params, model),
                        messages=messages,
                    )
        except RETRYABLE_ERRORS as e:
            logger.warning(
                "Gemini model %s failed after %d attempts: %s. Trying next model.",
                model,
                max_attempts_per_model,
                e,
            )
            last_exc = e
            continue

    # All models exhausted
    raise last_exc  # type: ignore[misc]
