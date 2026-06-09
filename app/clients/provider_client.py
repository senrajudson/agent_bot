from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings
from app.schemas.llm import LLMParams


def _get_ollama_llm(params: LLMParams) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    kwargs: dict[str, Any] = {
        "model": settings.OLLAMA_MODEL,
        "base_url": settings.OLLAMA_BASE_URL,
        "temperature": params.temperature,
    }

    if params.num_ctx is not None:
        kwargs["num_ctx"] = params.num_ctx

    if params.num_predict is not None:
        kwargs["num_predict"] = params.num_predict

    if params.top_k is not None:
        kwargs["top_k"] = params.top_k

    if params.top_p is not None:
        kwargs["top_p"] = params.top_p

    if params.repeat_penalty is not None:
        kwargs["repeat_penalty"] = params.repeat_penalty

    if params.seed is not None:
        kwargs["seed"] = params.seed

    if params.keep_alive is not None:
        kwargs["keep_alive"] = params.keep_alive

    if params.format is not None:
        kwargs["format"] = params.format

    if params.think is not None:
        kwargs["think"] = params.think

    return ChatOllama(**kwargs)


def _get_groq_llm(params: LLMParams) -> BaseChatModel:
    from langchain_groq import ChatGroq

    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY não configurada no .env.")

    kwargs: dict[str, Any] = {
        "model": settings.GROQ_MODEL,
        "api_key": settings.GROQ_API_KEY,
        "temperature": params.temperature,
    }

    if params.num_predict is not None:
        kwargs["max_tokens"] = params.num_predict

    if params.top_p is not None:
        kwargs["top_p"] = params.top_p

    return ChatGroq(**kwargs)


def _get_openai_compatible_llm(params: LLMParams) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    if not settings.OPENAI_COMPATIBLE_API_KEY:
        raise ValueError("OPENAI_COMPATIBLE_API_KEY não configurada no .env.")

    if not settings.OPENAI_COMPATIBLE_BASE_URL:
        raise ValueError("OPENAI_COMPATIBLE_BASE_URL não configurada no .env.")

    if not settings.OPENAI_COMPATIBLE_MODEL:
        raise ValueError("OPENAI_COMPATIBLE_MODEL não configurado no .env.")

    kwargs: dict[str, Any] = {
        "model": settings.OPENAI_COMPATIBLE_MODEL,
        "api_key": settings.OPENAI_COMPATIBLE_API_KEY,
        "base_url": settings.OPENAI_COMPATIBLE_BASE_URL,
        "temperature": params.temperature,
    }

    if params.num_predict is not None:
        kwargs["max_tokens"] = params.num_predict

    if params.top_p is not None:
        kwargs["top_p"] = params.top_p

    return ChatOpenAI(**kwargs)


def _get_gemini_llm(params: LLMParams) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurada no .env.")

    kwargs: dict[str, Any] = {
        "model": settings.GEMINI_MODEL,
        "google_api_key": settings.GEMINI_API_KEY,
        "temperature": params.temperature,
    }

    if params.num_predict is not None:
        kwargs["max_tokens"] = params.num_predict

    if params.top_p is not None:
        kwargs["top_p"] = params.top_p

    if params.top_k is not None:
        kwargs["top_k"] = params.top_k

    return ChatGoogleGenerativeAI(**kwargs)


def get_llm(params: LLMParams | None = None) -> BaseChatModel:
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


def get_structured_llm(
    schema: Any,
    params: LLMParams | None = None,
    method: str = "json_schema",
):
    return get_llm(params).with_structured_output(
        schema=schema,
        method=method,
    )