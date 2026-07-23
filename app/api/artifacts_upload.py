from __future__ import annotations

import tempfile
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.artifacts import _require_internal_token
from app.core.config import settings
from app.infrastructure.artifacts import save_and_register_artifact

router = APIRouter()


async def _read_with_limit(file: UploadFile, limit: int) -> BytesIO:
    spool = tempfile.SpooledTemporaryFile(max_size=65536)
    total = 0
    try:
        while chunk := await file.read(65536):
            total += len(chunk)
            if total > limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"Arquivo excede o limite máximo de {limit} bytes.",
                )
            spool.write(chunk)
        spool.seek(0)
        return spool
    except BaseException:
        spool.close()
        raise


@router.post("/upload", status_code=201, dependencies=[Depends(_require_internal_token)])
async def upload_artifact(
    file: UploadFile = File(...),
    filename: str = Form(..., min_length=1, max_length=255),
    mime_type: str = Form(..., min_length=1, max_length=127),
    kind: str = Form("artifact"),
    creator: str = Form("mcp_tool"),
    cleanup_after_send: bool = Form(False),
    caption: str | None = Form(None),
) -> dict:
    max_bytes = settings.AGENT_ARTIFACT_MAX_UPLOAD_BYTES
    file_stream = await _read_with_limit(file, max_bytes)

    try:
        result = await save_and_register_artifact(
            file_stream=file_stream,
            filename=filename,
            mime_type=mime_type,
            kind=kind,
            creator=creator,
            cleanup_after_send=cleanup_after_send,
        )
    finally:
        file_stream.close()

    if caption:
        result["caption"] = caption

    return result
