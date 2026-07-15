import logging
import time

import httpx

from app.embeddings.exceptions import (
    EmbeddingAuthError,
    EmbeddingDimensionMismatchError,
    EmbeddingTransientError,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {429, 500, 502, 503}
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [0.5, 1.0, 2.0]

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-2",
        vector_size: int = 768,
        batch_size: int = 32,
        timeout: float = 60.0,
    ):
        self._api_key = api_key
        self.model = model
        self.vector_size = vector_size
        self._batch_size = batch_size
        self._timeout = timeout

    def _build_url(self, endpoint: str) -> str:
        return (
            f"{_GEMINI_BASE_URL}/models/{self.model}:{endpoint}"
            f"?key={self._api_key}"
        )

    def _request(self, url: str, payload: dict) -> httpx.Response:
        last_exception: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = httpx.post(url, json=payload, timeout=self._timeout)
            except httpx.TimeoutException as exc:
                logger.warning(
                    "Gemini timeout (attempt %d/%d)", attempt, _MAX_RETRIES
                )
                last_exception = EmbeddingTransientError(str(exc))
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS[attempt - 1])
                continue

            if resp.status_code in (401, 403):
                raise EmbeddingAuthError(
                    f"Gemini API auth error {resp.status_code}: {resp.text[:200]}"
                )

            if resp.status_code in _RETRYABLE_STATUSES:
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "Gemini %d (attempt %d/%d), retrying in %.1fs",
                        resp.status_code, attempt, _MAX_RETRIES,
                        _BACKOFF_SECONDS[attempt - 1],
                    )
                    time.sleep(_BACKOFF_SECONDS[attempt - 1])
                    last_exception = EmbeddingTransientError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    continue
                raise EmbeddingTransientError(
                    f"Gemini API {resp.status_code} after "
                    f"{_MAX_RETRIES} attempts: {resp.text[:200]}"
                )

            resp.raise_for_status()
            return resp

        raise EmbeddingTransientError(
            f"Gemini API failed after {_MAX_RETRIES} attempts: {last_exception}"
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            requests = []
            for text in batch:
                requests.append({
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": self.vector_size,
                })

            url = self._build_url("batchEmbedContents")
            resp = self._request(url, {"requests": requests})
            data = resp.json()

            for emb in data.get("embeddings", []):
                all_embeddings.append(emb["values"])

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        url = self._build_url("embedContent")
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": self.vector_size,
        }
        resp = self._request(url, payload)
        data = resp.json()
        return data["embedding"]["values"]

    def validate_collection(self, qdrant_vector_size: int) -> None:
        if qdrant_vector_size != self.vector_size:
            raise EmbeddingDimensionMismatchError(
                f"Expected vector_size={self.vector_size}, "
                f"got {qdrant_vector_size}"
            )
