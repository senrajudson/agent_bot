"""Tests for RAG document temporal contract (T082).

Validates that CHUNK 27 and CHUNK 28 in PI_WEB_API_AGENT_GUIDE.md
correctly document the new temporal contract.
"""
from __future__ import annotations

import pytest
from pathlib import Path


RAG_FILE = Path(__file__).resolve().parent.parent.parent / "PI_WEB_API_AGENT_GUIDE.md"


class TestRagTemporalContract:
    """CHUNK 27 and CHUNK 28 document the new contract."""

    def _read_rag(self) -> str:
        return RAG_FILE.read_text(encoding="utf-8")

    def test_chunk27_contains_pi_tokens(self):
        content = self._read_rag()
        # Find CHUNK 27 section
        idx = content.find("# CHUNK 27")
        assert idx >= 0, "CHUNK 27 not found"
        chunk27 = content[idx:idx + 2000]
        assert "*-24h" in chunk27
        assert "*-1h" in chunk27
        assert "*-1d" in chunk27
        assert "T" in chunk27
        assert "Y" in chunk27
        assert "token temporal PI" in chunk27

    def test_chunk28_contains_pi_tokens(self):
        content = self._read_rag()
        idx = content.find("# CHUNK 28")
        assert idx >= 0, "CHUNK 28 not found"
        chunk28 = content[idx:idx + 2000]
        assert "*-24h" in chunk28
        assert "token temporal PI" in chunk28

    def test_chunk27_still_mentions_iso_8601(self):
        content = self._read_rag()
        idx = content.find("# CHUNK 27")
        chunk27 = content[idx:idx + 2000]
        assert "ISO 8601" in chunk27

    def test_chunk28_still_mentions_iso_8601(self):
        content = self._read_rag()
        idx = content.find("# CHUNK 28")
        chunk28 = content[idx:idx + 2000]
        assert "ISO 8601" in chunk28
