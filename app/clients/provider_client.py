"""
LLM Provider factory — Google ADK based.

Returns ADK `BaseLlm` instances for the configured provider:
- gemini       -> google.adk.models.google_llm.Gemini
- groq         -> google.adk.models.lite_llm.LiteLlm (model: groq/<model>)
- ollama       -> google.adk.models.lite_llm.LiteLlm (model: ollama_chat/<model>)
- openai_compatible -> google.adk.models.lite_llm.LiteLlm (model: openai/<model>)
"""

from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.google_llm import Gemini
from google.genai import types as genai_types

from app.core.config import settings
from app.schemas.llm import LLMParams


def _common_generation_config(params: LLMParams) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "temperature": params.temperature,
    }

    if params.num_predict is not None or params.max_tokens is not None:
        cfg["max_output_tokens"] = params.num_predict or params.max_tokens

    if params.top_p is not None:
        cfg["top_p"] = params.top_p

    if params.top_k is not None:
        cfg["top_k"] = params.top_k

    return cfg


def _get_gemini_llm(params: LLMParams) -> BaseLlm:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurada no .env.")

    generation_config = genai_types.GenerateContentConfig(
        **_common_generation_config(params),
    )

    return Gemini(
        model=settings.GEMINI_MODEL,
        api_key=settings.GEMINI_API_KEY,
        generation_config=generation_config,
    )


def _get_ollama_llm(params: LLMParams) -> BaseLlm:
    kwargs: dict[str, Any] = {
        "model": f"ollama_chat/{settings.OLLAMA_MODEL}",
        "api_base": settings.OLLAMA_BASE_URL,
        "temperature": params.temperature,
    }

    if params.num_predict is not None:
        kwargs["max_tokens"] = params.num_predict

    if params.top_p is not None:
        kwargs["top_p"] = params.top_p

    if params.top_k is not None:
        kwargs["top_k"] = params.top_k

    if params.seed is not None:
        kwargs["seed"] = params.seed

    if params.keep_alive is not None:
        keep_alive = str(params.keep_alive)
        if keep_alive.endswith("h") or keep_alive.endswith("m") or keep_alive.endswith("s"):
            keep_alive = f"{keep_alive[:-1]}m" if keep_alive.endswith("h") else keep_alive
        kwargs["keep_alive"] = keep_alive

    if params.format is not None:
        kwargs["format"] = params.format

    if params.num_ctx is not None:
        kwargs["num_ctx"] = params.num_ctx

    return LiteLlm(**kwargs)


def _get_groq_llm(params: LLMParams) -> BaseLlm:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY não configurada no .env.")

    kwargs: dict[str, Any] = {
        "model": f"groq/{settings.GROQ_MODEL}",
        "api_key": settings.GROQ_API_KEY,
        "temperature": params.temperature,
    }

    if params.num_predict is not None:
        kwargs["max_tokens"] = params.num_predict

    if params.top_p is not None:
        kwargs["top_p"] = params.top_p

    return LiteLlm(**kwargs)


def _get_openai_compatible_llm(params: LLMParams) -> BaseLlm:
    if not settings.OPENAI_COMPATIBLE_API_KEY:
        raise ValueError("OPENAI_COMPATIBLE_API_KEY não configurada no .env.")
    if not settings.OPENAI_COMPATIBLE_BASE_URL:
        raise ValueError("OPENAI_COMPATIBLE_BASE_URL não configurada no .env.")
    if not settings.OPENAI_COMPATIBLE_MODEL:
        raise ValueError("OPENAI_COMPATIBLE_MODEL não configurado no .env.")

    kwargs: dict[str, Any] = {
        "model": f"openai/{settings.OPENAI_COMPATIBLE_MODEL}",
        "api_key": settings.OPENAI_COMPATIBLE_API_KEY,
        "api_base": settings.OPENAI_COMPATIBLE_BASE_URL,
        "temperature": params.temperature,
    }

    if params.num_predict is not None:
        kwargs["max_tokens"] = params.num_predict

    if params.top_p is not None:
        kwargs["top_p"] = params.top_p

    return LiteLlm(**kwargs)


def get_llm(params: LLMParams | None = None) -> BaseLlm:
    params = params or LLMParams()
    provider = settings.LLM_PROVIDER.lower().strip()

    if provider == "ollama":
        return _get_ollama_llm(params)
    if provider == "groq":
        return _get_groq_llm(params)
    if provider in {"openai_compatible", "openai-compatible", "openai"}:
        return _get_openai_compatible_llm(params)
    if provider == "gemini":
        return _get_gemini_llm(params)

    raise ValueError(
        f"LLM_PROVIDER inválido: {settings.LLM_PROVIDER}. "
        "Use ollama, groq, openai_compatible ou gemini."
    )


def get_llm_for_model(params: LLMParams, model_name: str) -> BaseLlm:
    """Build ADK Gemini LLM for a specific model (used by pi_agent fallback)."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurada no .env.")

    generation_config = genai_types.GenerateContentConfig(
        **_common_generation_config(params),
    )

    return Gemini(
        model=model_name,
        api_key=settings.GEMINI_API_KEY,
        generation_config=generation_config,
    )
