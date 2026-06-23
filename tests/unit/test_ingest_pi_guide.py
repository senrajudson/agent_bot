"""Tests for scripts/ingest_pi_guide.py — chunk parsing and filtering."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.ingest_pi_guide import CHUNK_HEADER_RE, SKIP_CHUNK, parse_chunks


# ---------------------------------------------------------------------------
# parse_chunks
# ---------------------------------------------------------------------------
class TestParseChunks:
    def test_returns_list_of_dicts(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        assert isinstance(chunks, list)
        assert all(isinstance(c, dict) for c in chunks)

    def test_each_chunk_has_required_keys(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        for c in chunks:
            assert "chunk_number" in c
            assert "title" in c
            assert "content" in c

    def test_chunk_numbers_are_unique(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        numbers = [c["chunk_number"] for c in chunks]
        assert len(numbers) == len(set(numbers))

    def test_first_chunk_is_01(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        # No intro in sample → first chunk should be 01
        assert chunks[0]["chunk_number"] == 1

    def test_chunk_count_matches_headers(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        matches = CHUNK_HEADER_RE.findall(text)
        assert len(chunks) == len(matches)


# ---------------------------------------------------------------------------
# SKIP_CHUNK constant
# ---------------------------------------------------------------------------
class TestSkipChunk:
    def test_skip_chunk_is_one(self):
        assert SKIP_CHUNK == 1

    def test_skip_chunk_excludes_fixed_from_ingest(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        to_ingest = [c for c in chunks if c["chunk_number"] not in (0, SKIP_CHUNK)]
        chunk_numbers = [c["chunk_number"] for c in to_ingest]
        assert SKIP_CHUNK not in chunk_numbers
        assert 0 not in chunk_numbers

    def test_ingest_count_is_total_minus_fixed(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        to_ingest = [c for c in chunks if c["chunk_number"] not in (0, SKIP_CHUNK)]
        # Sample has no intro (chunk 0), so only CHUNK 01 is skipped
        expected = len([c for c in chunks if c["chunk_number"] != SKIP_CHUNK])
        assert len(to_ingest) == expected


# ---------------------------------------------------------------------------
# CHUNK 01 is the fixed context
# ---------------------------------------------------------------------------
class TestFixedChunkIs01:
    def test_chunk_01_title_contains_fixo(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        chunk_01 = next(c for c in chunks if c["chunk_number"] == 1)
        assert "fixo" in chunk_01["title"].lower() or "selecao" in chunk_01["title"].lower()

    def test_chunk_01_not_in_qdrant(self, sample_markdown):
        text = sample_markdown.read_text(encoding="utf-8")
        chunks = parse_chunks(text)
        to_ingest = [c for c in chunks if c["chunk_number"] not in (0, SKIP_CHUNK)]
        chunk_numbers = [c["chunk_number"] for c in to_ingest]
        # CHUNK 01 excluded, CHUNK 20 present
        assert 1 not in chunk_numbers
        assert 20 in chunk_numbers
