"""Tests for artifact upload, download, and validation."""
from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.artifacts import InMemoryArtifactStore, get_artifact_store
from app.infrastructure.artifacts.upload_service import (
    _basename_safe,
    _validate_magic_bytes,
    _validate_mime_and_ext,
    save_and_register_artifact,
)


# ── _basename_safe ──


class TestBasenameSafe:
    def test_removes_directory_traversal(self):
        assert _basename_safe("../../etc/passwd") == "passwd"

    def test_keeps_safe_chars(self):
        assert _basename_safe("hello_world.txt") == "hello_world.txt"

    def test_strips_spaces(self):
        assert _basename_safe("  file.txt ") == "file.txt"

    def test_fallback_to_unnamed(self):
        assert _basename_safe("") == "unnamed"


# ── _validate_magic_bytes ──


class TestValidateMagicBytes:
    def test_png_valid(self):
        _validate_magic_bytes(b"\x89PNG\r\n\x1a\n" + b"data", "image/png")

    def test_png_invalid(self):
        with pytest.raises(ValueError, match="magic bytes"):
            _validate_magic_bytes(b"notapng", "image/png")

    def test_jpeg_valid(self):
        data = b"\xff\xd8\xff" + b"\x00" * 100 + b"\xff\xd9"
        _validate_magic_bytes(data, "image/jpeg")

    def test_jpeg_invalid(self):
        with pytest.raises(ValueError, match="magic bytes"):
            _validate_magic_bytes(b"notajpeg", "image/jpeg")

    def test_pdf_valid(self):
        _validate_magic_bytes(b"%PDF-1.4", "application/pdf")

    def test_pdf_invalid(self):
        with pytest.raises(ValueError, match="magic bytes"):
            _validate_magic_bytes(b"notapdf", "application/pdf")

    def test_csv_binary_rejected(self):
        with pytest.raises(ValueError, match="binário"):
            _validate_magic_bytes(b"\x00\x01", "text/csv")

    def test_csv_text_accepted(self):
        _validate_magic_bytes(b"a,b,c\n1,2,3", "text/csv")

    def test_txt_binary_rejected(self):
        with pytest.raises(ValueError, match="binário"):
            _validate_magic_bytes(b"\x00\x01", "text/plain")

    def test_txt_text_accepted(self):
        _validate_magic_bytes(b"hello world", "text/plain")


# ── save_and_register_artifact ──


@pytest.mark.asyncio
async def test_upload_text_plain_succeeds():
    stream = BytesIO(b"hello world")
    result = await save_and_register_artifact(
        file_stream=stream,
        filename="test.txt",
        mime_type="text/plain",
    )
    assert "artifact_id" in result
    assert result["filename"] == "test.txt"
    assert result["mime_type"] == "text/plain"
    assert result["size_bytes"] == 11


@pytest.mark.asyncio
async def test_upload_csv_succeeds():
    stream = BytesIO(b"a,b,c\n1,2,3")
    result = await save_and_register_artifact(
        file_stream=stream,
        filename="data.csv",
        mime_type="text/csv",
    )
    assert result["mime_type"] == "text/csv"


@pytest.mark.asyncio
async def test_upload_invalid_mime_rejected():
    stream = BytesIO(b"{}")
    with pytest.raises(ValueError, match="MIME type"):
        await save_and_register_artifact(
            file_stream=stream,
            filename="data.json",
            mime_type="application/json",
        )


@pytest.mark.asyncio
async def test_upload_blocked_extension_rejected():
    stream = BytesIO(b"fake")
    for ext in (".exe", ".html", ".svg", ".zip"):
        with pytest.raises(ValueError, match="Extensão"):
            await save_and_register_artifact(
                file_stream=stream,
                filename=f"bad{ext}",
                mime_type="text/plain",
            )


@pytest.mark.asyncio
async def test_upload_filename_sanitized():
    stream = BytesIO(b"test")
    result = await save_and_register_artifact(
        file_stream=stream,
        filename="../safe_name.txt",
        mime_type="text/plain",
    )
    assert result["filename"] == "safe_name.txt"


@pytest.mark.asyncio
async def test_upload_png_magic_bytes_invalid_rejected():
    stream = BytesIO(b"notapngcontent")
    with pytest.raises(ValueError, match="magic bytes"):
        await save_and_register_artifact(
            file_stream=stream,
            filename="test.png",
            mime_type="image/png",
        )


@pytest.mark.asyncio
async def test_upload_jpeg_magic_bytes_invalid_rejected():
    stream = BytesIO(b"notajpegcontent")
    with pytest.raises(ValueError, match="magic bytes"):
        await save_and_register_artifact(
            file_stream=stream,
            filename="test.jpg",
            mime_type="image/jpeg",
        )


@pytest.mark.asyncio
async def test_upload_pdf_magic_bytes_succeeds():
    stream = BytesIO(b"%PDF-1.4 metadata")
    result = await save_and_register_artifact(
        file_stream=stream,
        filename="doc.pdf",
        mime_type="application/pdf",
    )
    assert result["mime_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_path_traversal_in_filename_sanitized():
    stream = BytesIO(b"test")
    result = await save_and_register_artifact(
        file_stream=stream,
        filename="../../etc/passwd",
        mime_type="text/plain",
    )
    assert result["filename"] == "passwd"


@pytest.mark.asyncio
async def test_upload_tempfile_removed_on_error():
    stream = BytesIO(b"test")
    with patch("app.infrastructure.artifacts.upload_service.os.replace",
               side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            await save_and_register_artifact(
                file_stream=stream,
                filename="fail.txt",
                mime_type="text/plain",
            )
    # The temp file should have been cleaned up by try/finally


# ── 404 / 410 through the store ──


@pytest.mark.asyncio
async def test_lookup_nonexistent_via_api_pattern():
    store = InMemoryArtifactStore()
    result = await store.lookup("no-such")
    assert result.artifact is None
    assert result.is_expired is False


@pytest.mark.asyncio
async def test_lookup_expired_via_api_pattern():
    store = InMemoryArtifactStore()
    from datetime import datetime, timezone, timedelta
    from app.infrastructure.artifacts import Artifact
    art = Artifact(
        artifact_id="expired",
        filename="x.txt",
        mime_type="text/plain",
        size_bytes=1,
        created_at=datetime.now(tz=timezone.utc) - timedelta(hours=2),
        expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    await store.register(art)
    now = datetime.now(tz=timezone.utc)
    result = await store.lookup("expired", now=now)
    assert result.artifact is None
    assert result.is_expired is True
