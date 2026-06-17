"""
CHUNK-based ingestion script for PI_WEB_API_AGENT_GUIDE.md into Qdrant.

Splits the document by CHUNK headers (# CHUNK 01, # CHUNK 02, etc.).
Chunk 20 is excluded (it's a fixed context chunk always injected at runtime).
Uses Ollama nomic-embed-text-v2-moe for embeddings.
"""

import re
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = settings.OLLAMA_EMBEDDING_MODEL
OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
QDRANT_URL = settings.QDRANT_URL
COLLECTION = settings.QDRANT_COLLECTION
MARKDOWN_PATH = Path(__file__).parent.parent / "PI_WEB_API_AGENT_GUIDE.md"

VECTOR_SIZE = 768  # nomic-embed-text-v2-moe produces 768-dim vectors
SKIP_CHUNK = 20  # Chunk 20 is always injected at runtime, not stored in Qdrant

# Pattern: # CHUNK 01 - Title, # CHUNK 02 - Title, etc.
CHUNK_HEADER_RE = re.compile(r"^#\s+CHUNK\s+(\d+)\s*-\s*(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# 1. Parse document into CHUNK-based sections
# ---------------------------------------------------------------------------
def parse_chunks(text: str) -> list[dict]:
    """
    Split the document by CHUNK headers.

    Returns list of dicts with keys: chunk_number, title, content.
    The intro (before first CHUNK) is returned as chunk_number=0.
    """
    # Find all chunk header positions
    matches = list(CHUNK_HEADER_RE.finditer(text))

    if not matches:
        raise ValueError("No CHUNK headers found in the document.")

    chunks: list[dict] = []

    # Intro: everything before the first CHUNK header
    intro_text = text[: matches[0].start()].strip()
    if intro_text:
        chunks.append({
            "chunk_number": 0,
            "title": "Intro",
            "content": intro_text,
        })

    # Each CHUNK section
    for i, match in enumerate(matches):
        chunk_num = int(match.group(1))
        title = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        chunks.append({
            "chunk_number": chunk_num,
            "title": f"CHUNK {chunk_num:02d} - {title}",
            "content": content,
        })

    return chunks


# ---------------------------------------------------------------------------
# 2. Embed texts via Ollama REST API
# ---------------------------------------------------------------------------
def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed texts using Ollama /api/embed endpoint."""
    import httpx

    url = f"{OLLAMA_BASE_URL}/api/embed"
    all_embeddings: list[list[float]] = []

    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = httpx.post(
            url,
            json={"model": EMBEDDING_MODEL, "input": batch},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        all_embeddings.extend(data["embeddings"])
        print(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks")

    return all_embeddings


# ---------------------------------------------------------------------------
# 3. Upsert into Qdrant
# ---------------------------------------------------------------------------
def upsert_chunks(chunks: list[dict], embeddings: list[list[float]]):
    """Create collection (if needed) and upsert all chunks."""
    client = QdrantClient(url=QDRANT_URL, timeout=120)

    # Delete collection if it exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION in collections:
        print(f"  Deleting existing collection '{COLLECTION}'")
        client.delete_collection(COLLECTION)

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    print(f"  Created collection '{COLLECTION}' (vector_size={VECTOR_SIZE}, distance=cosine)")

    # Build points — use chunk_number as the Qdrant point ID
    points = []
    for chunk, embedding in zip(chunks, embeddings):
        payload = {
            "content": chunk["content"],
            "title": chunk["title"],
            "chunk_number": chunk["chunk_number"],
            "source": "PI_WEB_API_AGENT_GUIDE.md",
        }

        points.append(
            PointStruct(
                id=chunk["chunk_number"],
                vector=embedding,
                payload=payload,
            )
        )

    # Batch upsert
    batch_size = 100
    for i in range(0, len(points), batch_size):
        client.upsert(
            collection_name=COLLECTION,
            points=points[i : i + batch_size],
        )

    print(f"  Upserted {len(points)} points into '{COLLECTION}'")

    # Verify
    info = client.get_collection(COLLECTION)
    print(f"  Collection info: {info.points_count} points, status={info.status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("PI Web API Guide — CHUNK-based Ingestion into Qdrant")
    print("=" * 60)

    # 1. Read markdown
    print(f"\n[1/3] Reading {MARKDOWN_PATH.name} ...")
    text = MARKDOWN_PATH.read_text(encoding="utf-8")
    print(f"  {len(text)} chars, {len(text.splitlines())} lines")

    # 2. Parse into CHUNKs
    print("\n[2/3] Parsing CHUNKs ...")
    all_chunks = parse_chunks(text)
    print(f"  Found {len(all_chunks)} chunks (including intro):")

    # Filter out the chunk to skip
    chunks_to_ingest = []
    for c in all_chunks:
        chunk_num = c["chunk_number"]
        marker = " [SKIP]" if chunk_num == SKIP_CHUNK else ""
        print(f"    [{chunk_num:2d}] {c['title'][:60]:<60} ({len(c['content'])} chars){marker}")
        if chunk_num != SKIP_CHUNK:
            chunks_to_ingest.append(c)

    print(f"\n  Ingesting {len(chunks_to_ingest)} chunks (skipping CHUNK {SKIP_CHUNK:02d})")

    # 3. Embed
    print(f"\n[3/3] Embedding with {EMBEDDING_MODEL} ...")
    texts = [c["content"] for c in chunks_to_ingest]
    embeddings = embed_texts(texts)
    print(f"  Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")

    # 4. Upsert
    print("\nUpserting into Qdrant ...")
    upsert_chunks(chunks_to_ingest, embeddings)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
