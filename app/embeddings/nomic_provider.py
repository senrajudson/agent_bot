import httpx

from app.embeddings.exceptions import EmbeddingDimensionMismatchError


class NomicProvider:
    name = "nomic"

    def __init__(
        self,
        ollama_base_url: str,
        model: str,
        vector_size: int = 768,
    ):
        self._ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.vector_size = vector_size

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._ollama_base_url}/api/embed"
        batch_size = 32
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = httpx.post(
                url,
                json={"model": self.model, "input": batch},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            all_embeddings.extend(data["embeddings"])

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def validate_collection(self, qdrant_vector_size: int) -> None:
        if qdrant_vector_size != self.vector_size:
            raise EmbeddingDimensionMismatchError(
                f"Expected vector_size={self.vector_size}, "
                f"got {qdrant_vector_size}"
            )
