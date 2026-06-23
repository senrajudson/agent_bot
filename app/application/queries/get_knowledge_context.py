"""Query: Get RAG knowledge context."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.queries.base import Query
from app.domain.protocols import KnowledgeRepository


@dataclass(frozen=True)
class GetKnowledgeContext(Query):
    """Request RAG knowledge context for a query string."""

    query: str
    top_k: int = 3
    include_fixed: bool = True


@dataclass(frozen=True)
class GetKnowledgeContextResult:
    """Result of knowledge context retrieval."""

    context: str


class GetKnowledgeContextHandler:
    """Retrieves RAG context from Qdrant-backed knowledge store.

    Delegates to a KnowledgeRepository (injected via constructor).
    No direct dependency on Qdrant, Ollama, or any infrastructure.
    """

    def __init__(self, knowledge_repo: KnowledgeRepository) -> None:
        self._repo = knowledge_repo

    async def handle(
        self, query: GetKnowledgeContext
    ) -> GetKnowledgeContextResult:
        context = self._repo.build_context(
            query=query.query,
            top_k=query.top_k,
            include_fixed=query.include_fixed,
        )
        return GetKnowledgeContextResult(context=context)
