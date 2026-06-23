"""Command: Retrieve RAG knowledge context for a query."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.application.commands.base import Command
from app.domain.protocols import KnowledgeRepository


@dataclass(frozen=True)
class RetrieveKnowledgeContext(Command):
    """Request RAG context retrieval for a user query."""

    query: str
    top_k: int = 3
    include_fixed: bool = True


@dataclass(frozen=True)
class RetrieveKnowledgeContextResult:
    """Result of knowledge retrieval."""

    context: str
    chunks_used: list[int] = field(default_factory=list)


class RetrieveKnowledgeContextHandler:
    """Retrieves RAG context by embedding the query and searching Qdrant.

    Delegates to a KnowledgeRepository (injected via constructor).
    No direct dependency on Qdrant, Ollama, or any infrastructure.
    """

    def __init__(self, knowledge_repo: KnowledgeRepository) -> None:
        self._repo = knowledge_repo

    async def handle(
        self, command: RetrieveKnowledgeContext
    ) -> RetrieveKnowledgeContextResult:
        context = self._repo.build_context(
            query=command.query,
            top_k=command.top_k,
            include_fixed=command.include_fixed,
        )
        chunks = self._repo.retrieve_relevant(command.query, command.top_k)
        return RetrieveKnowledgeContextResult(
            context=context,
            chunks_used=[c.chunk_number for c in chunks],
        )
