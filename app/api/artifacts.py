from __future__ import annotations

from datetime import datetime as _datetime
from hmac import compare_digest
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse

from app.core.config import settings
from app.infrastructure.artifacts import get_artifact_store

router = APIRouter()


def _require_internal_token(
    x_agent_token: str | None = Header(default=None),
) -> None:
    expected = settings.AGENT_ARTIFACT_TOKEN
    if not expected:
        raise HTTPException(status_code=401, detail="Token não configurado no servidor.")
    if not x_agent_token or not compare_digest(x_agent_token, expected):
        raise HTTPException(status_code=401, detail="Token inválido ou ausente.")


def _safe_path(path_str: str, base_dir: str) -> Path:
    resolved = Path(path_str).resolve()
    base = Path(base_dir).resolve()
    if not str(resolved).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Path inválido.")
    if resolved.is_symlink():
        raise HTTPException(status_code=400, detail="Symlink não permitido.")
    if not resolved.is_file():
        raise HTTPException(status_code=410, detail="Arquivo não disponível.")
    return resolved


def _build_metadata(artifact_id: str, artifact: Any) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "filename": artifact.filename,
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "created_at": _datetime.isoformat(artifact.created_at),
        "expires_at": _datetime.isoformat(artifact.expires_at),
        "cleanup_after_send": artifact.cleanup_after_send,
    }


@router.get("/{artifact_id}/metadata", dependencies=[Depends(_require_internal_token)])
async def get_artifact_metadata(artifact_id: str) -> dict[str, Any]:
    store = get_artifact_store()
    result = await store.lookup(artifact_id)
    if result.artifact is None and not result.is_expired:
        raise HTTPException(status_code=404, detail="Artifact não encontrado.")
    if result.artifact is None and result.is_expired:
        raise HTTPException(status_code=410, detail="Artifact expirado.")
    return _build_metadata(artifact_id, result.artifact)


@router.get("/{artifact_id}/download", dependencies=[Depends(_require_internal_token)])
async def download_artifact(artifact_id: str, request: Request) -> FileResponse:
    store = get_artifact_store()
    result = await store.lookup(artifact_id)
    if result.artifact is None and not result.is_expired:
        raise HTTPException(status_code=404, detail="Artifact não encontrado.")
    if result.artifact is None and result.is_expired:
        raise HTTPException(status_code=410, detail="Artifact expirado.")
    artifact_path = str(
        Path(settings.AGENT_ARTIFACTS_BASE_DIR)
        / result.artifact.artifact_id
        / result.artifact.filename
    )
    resolved = _safe_path(artifact_path, settings.AGENT_ARTIFACTS_BASE_DIR)
    safe_filename = quote(result.artifact.filename, safe="")
    return FileResponse(
        path=str(resolved),
        media_type=result.artifact.mime_type,
        filename=safe_filename,
    )


@router.delete("/{artifact_id}", dependencies=[Depends(_require_internal_token)])
async def delete_artifact(artifact_id: str) -> dict[str, Any]:
    store = get_artifact_store()
    removed = await store.delete(artifact_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Artifact não encontrado.")
    return {"ok": True}
