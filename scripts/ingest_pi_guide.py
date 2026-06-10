"""
Semantic chunking ingestion script for PI_WEB_API_AGENT_GUIDE.md into Qdrant.

Uses Ollama nomic-embed-text-v2-moe for embeddings.
Respects markdown structure: headers, code blocks, and tables stay intact.
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
MAX_CHUNK_CHARS = 1200  # target max chars per chunk


# ---------------------------------------------------------------------------
# 1. Parse markdown into semantic units
# ---------------------------------------------------------------------------
def _is_code_fence(line: str) -> bool:
    return line.strip().startswith("```")


def parse_markdown_sections(text: str) -> list[dict]:
    """
    Split markdown into semantic units based on header hierarchy.

    Returns list of dicts with keys: header, level, content.
    The top-level intro (before first ##) gets level=0.
    """
    lines = text.split("\n")
    sections: list[dict] = []
    current_header = "Introduction"
    current_level = 0
    current_lines: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # Track code fence state — never split inside a code block
        if _is_code_fence(stripped):
            in_code_block = not in_code_block
            current_lines.append(line)
            continue

        if in_code_block:
            current_lines.append(line)
            continue

        # Check for header
        header_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if header_match:
            # Save previous section
            if current_lines:
                sections.append({
                    "header": current_header,
                    "level": current_level,
                    "content": "\n".join(current_lines).strip(),
                })
            current_level = len(header_match.group(1))
            current_header = header_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Flush last section
    if current_lines:
        sections.append({
            "header": current_header,
            "level": current_level,
            "content": "\n".join(current_lines).strip(),
        })

    return sections


# ---------------------------------------------------------------------------
# 2. Merge small sections & split large ones (semantic chunking)
# ---------------------------------------------------------------------------
def _count_chars(sections: list[dict]) -> int:
    return sum(len(s["content"]) for s in sections)


def semantic_chunk(sections: list[dict], max_chars: int = MAX_CHUNK_CHARS) -> list[dict]:
    """
    Group small consecutive sections together and split large sections
    at ### boundaries. Always keeps code blocks and tables intact.
    """
    chunks: list[dict] = []
    buffer: list[dict] = []
    buffer_chars = 0

    def flush_buffer():
        nonlocal buffer, buffer_chars
        if not buffer:
            return
        merged_content = "\n\n".join(s["content"] for s in buffer)
        merged_headers = [s["header"] for s in buffer if s["header"] != "Introduction"]
        chunks.append({
            "section": merged_headers[0] if merged_headers else "Introduction",
            "subsection": merged_headers[-1] if len(merged_headers) > 1 else None,
            "content": merged_content,
        })
        buffer = []
        buffer_chars = 0

    for sec in sections:
        sec_len = len(sec["content"])

        # If this single section is too large, split at ### boundaries
        if sec_len > max_chars and sec["level"] >= 2:
            flush_buffer()
            sub_chunks = _split_large_section(sec, max_chars)
            chunks.extend(sub_chunks)
            continue

        # If adding this section would exceed the limit, flush first
        if buffer_chars + sec_len > max_chars and buffer:
            flush_buffer()

        buffer.append(sec)
        buffer_chars += sec_len

    flush_buffer()
    return chunks


def _split_large_section(section: dict, max_chars: int) -> list[dict]:
    """Split a large section into sub-chunks at ### or code block boundaries."""
    lines = section["content"].split("\n")
    sub_chunks: list[dict] = []
    current_lines: list[str] = []
    current_chars = 0
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        if _is_code_fence(stripped):
            in_code_block = not in_code_block
            current_lines.append(line)
            current_chars += len(line) + 1
            continue

        if in_code_block:
            current_lines.append(line)
            current_chars += len(line) + 1
            continue

        # Check for ### sub-header split point
        sub_header = re.match(r"^###\s+(.+)$", stripped)
        if sub_header and current_chars > 100:
            content = "\n".join(current_lines).strip()
            if content:
                sub_chunks.append({
                    "section": section["header"],
                    "subsection": sub_chunks[-1]["subsection"] if sub_chunks else None,
                    "content": content,
                })
            current_lines = [line]
            current_chars = len(line) + 1
            continue

        current_lines.append(line)
        current_chars += len(line) + 1

        # If we've gone over limit, split at next paragraph break
        if current_chars > max_chars and stripped == "":
            content = "\n".join(current_lines).strip()
            if content:
                sub_chunks.append({
                    "section": section["header"],
                    "subsection": None,
                    "content": content,
                })
            current_lines = []
            current_chars = 0

    # Flush remaining
    content = "\n".join(current_lines).strip()
    if content:
        sub_chunks.append({
            "section": section["header"],
            "subsection": None,
            "content": content,
        })

    return sub_chunks


# ---------------------------------------------------------------------------
# 3. Generate embeddings via Ollama REST API (no langchain needed)
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
# 4. Upsert into Qdrant
# ---------------------------------------------------------------------------
def upsert_chunks(chunks: list[dict], embeddings: list[list[float]]):
    """Create collection (if needed) and upsert all chunks."""
    client = QdrantClient(url=QDRANT_URL)

    # Create collection if it doesn't exist
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION in collections:
        print(f"  Collection '{COLLECTION}' already exists — deleting and recreating")
        client.delete_collection(COLLECTION)

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    print(f"  Created collection '{COLLECTION}' (vector_size={VECTOR_SIZE}, distance=cosine)")

    # Build points
    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        payload = {
            "content": chunk["content"],
            "section": chunk["section"],
            "source": "PI_WEB_API_AGENT_GUIDE.md",
        }
        if chunk.get("subsection"):
            payload["subsection"] = chunk["subsection"]

        points.append(
            PointStruct(
                id=i + 1,
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
    print("PI Web API Guide — Semantic Ingestion into Qdrant")
    print("=" * 60)

    # 1. Read markdown
    print(f"\n[1/4] Reading {MARKDOWN_PATH.name} ...")
    text = MARKDOWN_PATH.read_text(encoding="utf-8")
    print(f"  {len(text)} chars, {len(text.splitlines())} lines")

    # 2. Parse into semantic sections
    print("\n[2/4] Parsing semantic sections ...")
    sections = parse_markdown_sections(text)
    print(f"  Found {len(sections)} raw sections:")
    for s in sections:
        print(f"    {'#' * s['level']} {s['header'][:60]:<60} ({len(s['content'])} chars)")

    # 3. Semantic chunking
    print(f"\n[3/4] Semantic chunking (max {MAX_CHUNK_CHARS} chars/chunk) ...")
    chunks = semantic_chunk(sections)
    print(f"  Produced {len(chunks)} semantic chunks:")
    for i, c in enumerate(chunks):
        sub = f" > {c['subsection']}" if c.get("subsection") else ""
        print(f"    [{i+1:2d}] {c['section']}{sub}  ({len(c['content'])} chars)")

    # 4. Embed
    print(f"\n[4/4] Embedding with {EMBEDDING_MODEL} ...")
    texts = [c["content"] for c in chunks]
    embeddings = embed_texts(texts)
    print(f"  Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")

    # 5. Upsert
    print("\nUpserting into Qdrant ...")
    upsert_chunks(chunks, embeddings)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
