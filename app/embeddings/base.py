from dataclasses import dataclass
from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    model: str
    vector_size: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def validate_collection(self, qdrant_vector_size: int) -> None: ...


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    provider: str
