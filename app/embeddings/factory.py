import logging

from app.embeddings.base import EmbeddingProvider
from app.embeddings.exceptions import EmbeddingConfigError
from app.embeddings.gemini_provider import GeminiProvider
from app.embeddings.nomic_provider import NomicProvider

logger = logging.getLogger(__name__)


def get_embedding_provider(cfg) -> EmbeddingProvider:
    provider_name = cfg.EMBEDDING_PROVIDER

    if provider_name == "nomic":
        provider = NomicProvider(
            ollama_base_url=cfg.OLLAMA_BASE_URL,
            model=cfg.OLLAMA_EMBEDDING_MODEL,
            vector_size=cfg.EMBEDDING_VECTOR_SIZE,
        )
        logger.info(
            "Embedding provider: nomic (model=%s, vector_size=%d, collection=%s)",
            provider.model, provider.vector_size, cfg.QDRANT_COLLECTION,
        )
        return provider

    if provider_name == "gemini":
        if not cfg.GEMINI_API_KEY:
            raise EmbeddingConfigError(
                "GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini"
            )
        provider = GeminiProvider(
            api_key=cfg.GEMINI_API_KEY,
            model=cfg.GEMINI_EMBEDDING_MODEL or "gemini-embedding-2",
            vector_size=cfg.EMBEDDING_VECTOR_SIZE,
            batch_size=cfg.EMBEDDING_BATCH_SIZE,
            timeout=cfg.EMBEDDING_TIMEOUT_SECONDS,
        )
        logger.info(
            "Embedding provider: gemini (model=%s, vector_size=%d, batch_size=%d, "
            "timeout=%.1f, collection=%s)",
            provider.model, provider.vector_size, provider._batch_size,
            provider._timeout, cfg.QDRANT_COLLECTION,
        )
        return provider

    raise EmbeddingConfigError(
        f"Unknown EMBEDDING_PROVIDER: {provider_name!r}. "
        f"Expected 'nomic' or 'gemini'."
    )
