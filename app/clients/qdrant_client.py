"""
Qdrant retrieval client for PI Web API documentation RAG.

Embeds user queries via the configured embedding provider and searches
the Qdrant vector store for relevant documentation chunks.
"""

import logging
import re
from pathlib import Path

from qdrant_client import QdrantClient

from app.core.config import settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import get_embedding_provider
from app.embeddings.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QDRANT_URL = settings.QDRANT_URL
COLLECTION = settings.QDRANT_COLLECTION

DOCUMENT_PATH = Path(__file__).parent.parent.parent / "PI_WEB_API_AGENT_GUIDE.md"

# ---------------------------------------------------------------------------
# Clients (lazy singletons)
# ---------------------------------------------------------------------------
_qdrant_client: QdrantClient | None = None
_embedding_provider: EmbeddingProvider | None = None


def _get_qdrant() -> QdrantClient:
    global _qdrant_client

    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QDRANT_URL)

    return _qdrant_client


def _get_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = get_embedding_provider(settings)
        logger.info(
            "RAG embedding provider: %s (model=%s, vector_size=%d, collection=%s)",
            _embedding_provider.name,
            _embedding_provider.model,
            _embedding_provider.vector_size,
            COLLECTION,
        )
    return _embedding_provider


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
def _embed_query(text: str) -> list[float]:
    try:
        provider = _get_provider()
        return provider.embed_query(text)
    except EmbeddingError:
        logger.exception("Embedding query failed, returning empty vector")
        return []


# ---------------------------------------------------------------------------
# Fixed context chunk (always injected, not stored in Qdrant)
# ---------------------------------------------------------------------------
FIXED_CHUNK_NUMBER = 1  # CHUNK 01 is the fixed runtime context
_FIXED_CHUNK_CACHE: str | None = None

_FIXED_CHUNK_RE = re.compile(
    rf"# CHUNK {FIXED_CHUNK_NUMBER:02d} - .+?\n(.*?)(?=\n# |\Z)", re.DOTALL
)


def _load_fixed_chunk() -> str:
    """Load the fixed context chunk (CHUNK 01) from the markdown (cached)."""
    global _FIXED_CHUNK_CACHE

    if _FIXED_CHUNK_CACHE is not None:
        return _FIXED_CHUNK_CACHE

    text = DOCUMENT_PATH.read_text(encoding="utf-8")
    match = _FIXED_CHUNK_RE.search(text)

    if not match:
        _FIXED_CHUNK_CACHE = ""
        return _FIXED_CHUNK_CACHE

    _FIXED_CHUNK_CACHE = match.group(0).strip()
    return _FIXED_CHUNK_CACHE


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def retrieve_relevant_chunks(
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """
    Embed the query and search Qdrant for the most relevant chunks.

    Returns list of dicts with keys: chunk_number, title, content, score.
    """
    query_vector = _embed_query(query)

    client = _get_qdrant()
    results = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    )

    chunks = []
    for hit in results.points:
        payload = hit.payload
        chunks.append({
            "chunk_number": payload.get("chunk_number"),
            "title": payload.get("title", ""),
            "content": payload.get("content", ""),
            "score": hit.score,
        })

    return chunks


def build_rag_context(
    query: str,
    top_k: int = 3,
    include_fixed_chunk: bool = True,
) -> str:
    """
    Build a RAG context string from retrieved chunks + fixed context chunk (CHUNK 01).

    The result is a single string to prepend to the user message.
    """
    parts = []

    # Fixed context chunk (CHUNK 01)
    if include_fixed_chunk:
        fixed_chunk = _load_fixed_chunk()
        if fixed_chunk:
            parts.append(fixed_chunk)

    # Retrieved chunks
    retrieved = retrieve_relevant_chunks(query, top_k=top_k)

    for chunk in retrieved:
        parts.append(chunk["content"])

    if not parts:
        return ""

    return (
        "---\n"
        "CONTEXTO DA DOCUMENTAÇÃO PI WEB API (use para orientar suas respostas):\n"
        "---\n\n"
        + "\n\n---\n\n".join(parts)
    )
