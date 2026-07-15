class EmbeddingError(Exception):
    """Base for all embedding-related errors."""


class EmbeddingAuthError(EmbeddingError):
    """Authentication failure (401/403) — fail-fast, no retry."""


class EmbeddingTransientError(EmbeddingError):
    """Transient error (5xx/429) — retryable."""


class EmbeddingConfigError(EmbeddingError):
    """Bad configuration (invalid provider, missing API key)."""


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Vector dimension mismatch between provider and Qdrant collection."""
