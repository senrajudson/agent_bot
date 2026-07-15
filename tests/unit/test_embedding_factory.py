"""Tests for app/embeddings/factory.py — get_embedding_provider."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.embeddings.exceptions import EmbeddingConfigError
from app.embeddings.factory import get_embedding_provider
from app.embeddings.gemini_provider import GeminiProvider
from app.embeddings.nomic_provider import NomicProvider


def _make_settings(**overrides):
    settings = MagicMock()
    settings.EMBEDDING_PROVIDER = overrides.get("EMBEDDING_PROVIDER", "nomic")
    settings.OLLAMA_BASE_URL = overrides.get("OLLAMA_BASE_URL", "http://ollama:11434")
    settings.OLLAMA_EMBEDDING_MODEL = overrides.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text-v2-moe")
    settings.QDRANT_COLLECTION = overrides.get("QDRANT_COLLECTION", "pi_web_api_guide")
    settings.GEMINI_API_KEY = overrides.get("GEMINI_API_KEY", None)
    settings.GEMINI_EMBEDDING_MODEL = overrides.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
    settings.EMBEDDING_VECTOR_SIZE = overrides.get("EMBEDDING_VECTOR_SIZE", 768)
    settings.EMBEDDING_BATCH_SIZE = overrides.get("EMBEDDING_BATCH_SIZE", 32)
    settings.EMBEDDING_TIMEOUT_SECONDS = overrides.get("EMBEDDING_TIMEOUT_SECONDS", 60.0)
    return settings


class TestGetEmbeddingProvider:
    def test_nomic_returns_nomic_provider(self):
        settings = _make_settings()
        provider = get_embedding_provider(settings)
        assert isinstance(provider, NomicProvider)
        assert provider.name == "nomic"

    def test_gemini_with_key_returns_gemini_provider(self):
        settings = _make_settings(
            EMBEDDING_PROVIDER="gemini",
            GEMINI_API_KEY="test-key",
        )
        provider = get_embedding_provider(settings)
        assert isinstance(provider, GeminiProvider)
        assert provider.name == "gemini"

    def test_gemini_without_key_raises_config_error(self):
        settings = _make_settings(
            EMBEDDING_PROVIDER="gemini",
            GEMINI_API_KEY=None,
        )
        with pytest.raises(EmbeddingConfigError) as exc:
            get_embedding_provider(settings)
        assert "GEMINI_API_KEY is required" in str(exc.value)

    def test_unknown_provider_raises_config_error(self):
        settings = _make_settings(EMBEDDING_PROVIDER="invalid")
        with pytest.raises(EmbeddingConfigError) as exc:
            get_embedding_provider(settings)
        assert "Unknown EMBEDDING_PROVIDER" in str(exc.value)
