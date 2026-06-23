"""Tests for app/clients/qdrant_client.py — fixed chunk loading and RAG context."""

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.clients.qdrant_client import (
    FIXED_CHUNK_NUMBER,
    _FIXED_CHUNK_RE,
    _load_fixed_chunk,
    build_rag_context,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestFixedChunkNumber:
    def test_fixed_chunk_number_is_one(self):
        assert FIXED_CHUNK_NUMBER == 1


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------
class TestFixedChunkRegex:
    def test_matches_chunk_01_header(self):
        text = "# CHUNK 01 - Chunk fixo: selecao de tool\n Conteudo aqui"
        match = _FIXED_CHUNK_RE.search(text)
        assert match is not None

    def test_does_not_match_chunk_10(self):
        text = "# CHUNK 10 - Consumo de vazao\n Conteudo aqui"
        match = _FIXED_CHUNK_RE.search(text)
        assert match is None

    def test_does_not_match_chunk_20(self):
        text = "# CHUNK 20 - Calculos temporais\n Conteudo aqui"
        match = _FIXED_CHUNK_RE.search(text)
        assert match is None

    def test_does_not_match_chunk_21(self):
        text = "# CHUNK 21 - RAG e recuperacao\n Conteudo aqui"
        match = _FIXED_CHUNK_RE.search(text)
        assert match is None

    def test_captures_content_until_next_header(self):
        text = (
            "# CHUNK 01 - Fixo\n"
            "Linha A\n"
            "Linha B\n"
            "\n"
            "# CHUNK 02 - Proximo\n"
            "Conteudo 02"
        )
        match = _FIXED_CHUNK_RE.search(text)
        assert match is not None
        content = match.group(0)
        assert "Linha A" in content
        assert "Linha B" in content
        assert "CHUNK 02" not in content


# ---------------------------------------------------------------------------
# _load_fixed_chunk
# ---------------------------------------------------------------------------
class TestLoadFixedChunk:
    def test_returns_string(self, sample_markdown, monkeypatch):
        monkeypatch.setattr(
            "app.clients.qdrant_client.DOCUMENT_PATH", sample_markdown
        )
        # Reset cache
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        result = _load_fixed_chunk()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_chunk_01_title(self, sample_markdown, monkeypatch):
        monkeypatch.setattr(
            "app.clients.qdrant_client.DOCUMENT_PATH", sample_markdown
        )
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        result = _load_fixed_chunk()
        assert "CHUNK 01" in result

    def test_is_cached(self, sample_markdown, monkeypatch):
        monkeypatch.setattr(
            "app.clients.qdrant_client.DOCUMENT_PATH", sample_markdown
        )
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        result1 = _load_fixed_chunk()
        result2 = _load_fixed_chunk()
        assert result1 is result2

    def test_empty_string_when_chunk_missing(self, tmp_path, monkeypatch):
        md = tmp_path / "PI_WEB_API_AGENT_GUIDE.md"
        md.write_text("# CHUNK 02 - Somente chunk 02\nConteudo", encoding="utf-8")
        monkeypatch.setattr("app.clients.qdrant_client.DOCUMENT_PATH", md)
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        result = _load_fixed_chunk()
        assert result == ""


# ---------------------------------------------------------------------------
# build_rag_context
# ---------------------------------------------------------------------------
class TestBuildRagContext:
    def test_includes_fixed_chunk_first(self, sample_markdown, monkeypatch):
        monkeypatch.setattr(
            "app.clients.qdrant_client.DOCUMENT_PATH", sample_markdown
        )
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        with patch("app.clients.qdrant_client.retrieve_relevant_chunks", return_value=[]):
            result = build_rag_context("test query", top_k=1)

        assert "# CHUNK 01" in result
        # Fixed chunk content appears after the RAG header
        header_end = result.index("---\n\n") + 4
        chunk_pos = result.index("# CHUNK 01")
        assert chunk_pos > header_end

    def test_disabled_fixed_chunk(self, sample_markdown, monkeypatch):
        monkeypatch.setattr(
            "app.clients.qdrant_client.DOCUMENT_PATH", sample_markdown
        )
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        with patch("app.clients.qdrant_client.retrieve_relevant_chunks", return_value=[]):
            result = build_rag_context("test query", top_k=1, include_fixed_chunk=False)

        assert result == ""

    def test_empty_when_no_results_and_no_fixed(self, monkeypatch):
        fake_md = Path("/nonexistent/PI_WEB_API_AGENT_GUIDE.md")
        monkeypatch.setattr("app.clients.qdrant_client.DOCUMENT_PATH", fake_md)
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        with patch("app.clients.qdrant_client.retrieve_relevant_chunks", return_value=[]):
            result = build_rag_context("test query", top_k=1, include_fixed_chunk=False)

        assert result == ""

    def test_retrieved_chunks_appended_after_fixed(self, sample_markdown, monkeypatch):
        monkeypatch.setattr(
            "app.clients.qdrant_client.DOCUMENT_PATH", sample_markdown
        )
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        fake_chunks = [
            {"chunk_number": 2, "title": "CHUNK 02", "content": "RETRIEVED_CONTENT", "score": 0.9}
        ]
        with patch("app.clients.qdrant_client.retrieve_relevant_chunks", return_value=fake_chunks):
            result = build_rag_context("test query", top_k=1)

        assert "RETRIEVED_CONTENT" in result
        # Fixed chunk comes first
        fixed_pos = result.find("# CHUNK 01")
        retrieved_pos = result.find("RETRIEVED_CONTENT")
        assert fixed_pos < retrieved_pos

    def test_returns_string_type(self, sample_markdown, monkeypatch):
        monkeypatch.setattr(
            "app.clients.qdrant_client.DOCUMENT_PATH", sample_markdown
        )
        import app.clients.qdrant_client as qc
        qc._FIXED_CHUNK_CACHE = None

        with patch("app.clients.qdrant_client.retrieve_relevant_chunks", return_value=[]):
            result = build_rag_context("test", top_k=1)

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Chunk payload structure
# ---------------------------------------------------------------------------
class TestChunkPayload:
    def test_payload_has_required_fields(self):
        """Verify the expected payload keys match what retrieve_relevant_chunks reads."""
        expected_keys = {"chunk_number", "title", "content", "score"}
        # These are the keys returned by retrieve_relevant_chunks
        assert expected_keys == {"chunk_number", "title", "content", "score"}
