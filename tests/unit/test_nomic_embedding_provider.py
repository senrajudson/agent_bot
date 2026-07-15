"""Tests for app/embeddings/nomic_provider.py — NomicProvider."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.embeddings.nomic_provider import NomicProvider


@pytest.fixture
def provider():
    return NomicProvider(
        ollama_base_url="http://ollama:11434",
        model="nomic-embed-text-v2-moe",
        vector_size=768,
    )


class TestNomicProvider:
    def test_embed_query_returns_768_dim(self, provider):
        fake_response = {"embeddings": [[0.1] * 768]}
        with patch("app.embeddings.nomic_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            result = provider.embed_query("test query")

        assert len(result) == 768
        assert result == [0.1] * 768

    def test_embed_texts_returns_batch(self, provider):
        texts = ["a", "b"]
        fake_response = {"embeddings": [[0.1] * 768, [0.2] * 768]}
        with patch("app.embeddings.nomic_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            results = provider.embed_texts(texts)

        assert len(results) == 2
        assert results[0] == [0.1] * 768
        assert results[1] == [0.2] * 768

    def test_embed_query_routes_to_ollama(self, provider):
        fake_response = {"embeddings": [[0.5] * 768]}
        with patch("app.embeddings.nomic_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            provider.embed_query("test")

        # Verify the URL and model parameters
        call_kwargs = mock_post.call_args[1]
        assert "http://ollama:11434/api/embed" in str(mock_post.call_args[0])
        assert call_kwargs["json"]["model"] == "nomic-embed-text-v2-moe"
        assert call_kwargs["json"]["input"] == ["test"]

    def test_raises_on_http_error(self, provider):
        with patch("app.embeddings.nomic_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 500
            mock_post.return_value.raise_for_status.side_effect = Exception("HTTP 500")

            with pytest.raises(Exception):
                provider.embed_query("test")

    def test_validate_collection_matches(self, provider):
        provider.validate_collection(768)

    def test_validate_collection_mismatch(self, provider):
        with pytest.raises(Exception) as exc:
            provider.validate_collection(1024)
        assert "Expected vector_size=768, got 1024" in str(exc.value)

    def test_name_and_model(self, provider):
        assert provider.name == "nomic"
        assert provider.model == "nomic-embed-text-v2-moe"
        assert provider.vector_size == 768
