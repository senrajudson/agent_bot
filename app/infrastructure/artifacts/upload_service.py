from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.core.config import settings
from app.infrastructure.artifacts import Artifact, get_artifact_store, now_utc


ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/csv",
    "application/pdf",
    "image/png",
    "image/jpeg",
}

BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".sh", ".dll", ".cmd", ".com", ".scr",
    ".html", ".htm", ".svg", ".zip", ".tar", ".gz", ".7z", ".rar",
}


def _basename_safe(filename: str) -> str:
    name = Path(filename).name
    name = "".join(c for c in name if c.isalnum() or c in "._- ")
    return name.strip() or "unnamed"


def _extensions_from_filename(filename: str) -> list[str]:
    parts = filename.lower().split(".")
    if len(parts) < 2:
        return []
    return [f".{p}" for p in parts[1:]]


def _validate_mime_and_ext(
    filename: str, mime_type: str, file_bytes: bytes
) -> None:
    mime_lower = mime_type.lower().strip()
    if mime_lower not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"MIME type '{mime_type}' não permitido. "
            f"Permitidos: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )
    exts = _extensions_from_filename(filename)
    for ext in exts:
        if ext in BLOCKED_EXTENSIONS:
            raise ValueError(
                f"Extensão '{ext}' não permitida para o arquivo '{filename}'."
            )
    _validate_magic_bytes(file_bytes, mime_lower)


def _validate_magic_bytes(data: bytes, mime_type: str) -> None:
    if mime_type == "image/png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Conteúdo não corresponde a image/png (magic bytes inválidos).")
    elif mime_type == "image/jpeg":
        if not (data.startswith(b"\xff\xd8\xff") and b"\xff\xd9" in data[-4:]):
            raise ValueError("Conteúdo não corresponde a image/jpeg (magic bytes inválidos).")
    elif mime_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("Conteúdo não corresponde a application/pdf (magic bytes inválidos).")
    elif mime_type == "text/csv":
        if data.startswith(b"\x00"):
            raise ValueError("Conteúdo não corresponde a text/csv (arquivo binário).")
    elif mime_type == "text/plain":
        if data.startswith(b"\x00"):
            raise ValueError("Conteúdo não corresponde a text/plain (arquivo binário).")


def serialize_artifact_as_attachment(artifact: Artifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "filename": artifact.filename,
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "cleanup_after_send": artifact.cleanup_after_send,
        "caption": None,
    }


async def save_and_register_artifact(
    *,
    file_stream: BytesIO,
    filename: str,
    mime_type: str,
    kind: str = "artifact",
    creator: str = "mcp_tool",
    cleanup_after_send: bool = False,
) -> dict[str, Any]:
    safe_name = _basename_safe(filename)
    file_bytes = file_stream.read()
    _validate_mime_and_ext(safe_name, mime_type, file_bytes)

    artifact_id = uuid.uuid4().hex
    base_dir = Path(settings.AGENT_ARTIFACTS_BASE_DIR)
    artifact_dir = base_dir / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    final_path = (artifact_dir / safe_name).resolve()
    if not str(final_path).startswith(str(base_dir.resolve())):
        raise ValueError("Path traversal detectado.")

    if final_path.is_symlink() or final_path.exists():
        raise ValueError("Arquivo já existe ou é symlink.")

    tmp = NamedTemporaryFile(
        dir=str(artifact_dir),
        delete=False,
        suffix=f".{safe_name.split('.')[-1]}" if "." in safe_name else None,
    )
    try:
        tmp.write(file_bytes)
        tmp.close()
        os.replace(tmp.name, str(final_path))
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise

    size_bytes = final_path.stat().st_size
    created_at = now_utc()
    expires_at = created_at + timedelta(seconds=settings.AGENT_ARTIFACT_TTL_SECONDS)

    artifact = Artifact(
        artifact_id=artifact_id,
        filename=safe_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        created_at=created_at,
        expires_at=expires_at,
        cleanup_after_send=cleanup_after_send,
        kind=kind,
        owner=creator,
    )

    store = get_artifact_store()
    await store.register(artifact)

    return serialize_artifact_as_attachment(artifact)
