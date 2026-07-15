"""Tests for app/embeddings/gemini_provider.py — GeminiProvider."""

import sys
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.embeddings.exceptions import EmbeddingAuthError, EmbeddingTransientError
from app.embeddings.gemini_provider import GeminiProvider


@pytest.fixture
def provider():
    return GeminiProvider(
        api_key="test-key",
        model="gemini-embedding-2",
        vector_size=768,
        batch_size=32,
        timeout=10.0,
    )


class TestGeminiProvider:
    def test_embed_query_returns_768_dim(self, provider):
        fake_response = {"embedding": {"values": [0.1] * 768}}
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            result = provider.embed_query("test query")

        assert len(result) == 768

    def test_embed_query_payload_has_output_dimensionality(self, provider):
        fake_response = {"embedding": {"values": [0.1] * 768}}
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            provider.embed_query("test")

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["outputDimensionality"] == 768

    def test_embed_texts_batch(self, provider):
        texts = ["a", "b"]
        fake_response = {
            "embeddings": [
                {"values": [0.1] * 768},
                {"values": [0.2] * 768},
            ]
        }
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            results = provider.embed_texts(texts)

        assert len(results) == 2
        assert results[0] == [0.1] * 768
        assert results[1] == [0.2] * 768

    def test_retry_on_500(self, provider):
        fake_response = {"embedding": {"values": [0.1] * 768}}
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.side_effect = [
                _make_response(500),
                _make_response(500),
                _make_response(200, fake_response),
            ]

            result = provider.embed_query("test")

        assert len(result) == 768
        assert mock_post.call_count == 3

    def test_retry_on_429(self, provider):
        fake_response = {"embedding": {"values": [0.1] * 768}}
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.side_effect = [
                _make_response(429),
                _make_response(429),
                _make_response(200, fake_response),
            ]

            result = provider.embed_query("test")

        assert len(result) == 768
        assert mock_post.call_count == 3

    def test_fail_fast_on_401(self, provider):
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value = _make_response(401)

            with pytest.raises(EmbeddingAuthError):
                provider.embed_query("test")

        assert mock_post.call_count == 1

    def test_fail_fast_on_403(self, provider):
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value = _make_response(403)

            with pytest.raises(EmbeddingAuthError):
                provider.embed_query("test")

        assert mock_post.call_count == 1

    def test_exhausts_retries_and_raises(self, provider):
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value = _make_response(500)

            with pytest.raises(EmbeddingTransientError):
                provider.embed_query("test")

        assert mock_post.call_count == 3

    def test_validate_collection_matches(self, provider):
        provider.validate_collection(768)

    def test_validate_collection_mismatch(self, provider):
        with pytest.raises(Exception) as exc:
            provider.validate_collection(1024)
        assert "Expected vector_size=768, got 1024" in str(exc.value)

    def test_embed_query_endpoint_is_embed_content(self, provider):
        fake_response = {"embedding": {"values": [0.1] * 768}}
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            provider.embed_query("test")

        call_args = mock_post.call_args[0][0]
        assert "embedContent" in call_args

    def test_embed_texts_endpoint_is_batch_embed_contents(self, provider):
        fake_response = {"embeddings": [{"values": [0.1] * 768}]}
        with patch("app.embeddings.gemini_provider.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response

            provider.embed_texts(["test"])

        call_args = mock_post.call_args[0][0]
        assert "batchEmbedContents" in call_args

    def test_name_and_model(self, provider):
        assert provider.name == "gemini"
        assert provider.model == "gemini-embedding-2"
        assert provider.vector_size == 768


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None):
        self.status_code = status_code
        self.text = f"HTTP {status_code}" if status_code >= 400 else ""
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(self.text)

    def json(self):
        return self._json_data


def _make_response(status_code: int, json_data=None):
    return _FakeResponse(status_code, json_data)
