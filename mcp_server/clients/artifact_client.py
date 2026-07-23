from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Any

import httpx

logger = logging.getLogger("mcp_server.artifact_client")


class ArtifactUploadError(Exception):
    pass


class ArtifactAuthError(ArtifactUploadError):
    pass


class ArtifactSizeError(ArtifactUploadError):
    pass


class ArtifactServerError(ArtifactUploadError):
    pass


class ArtifactClient:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        timeout: float = 60.0,
        max_bytes: int = 26214400,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._max_bytes = max_bytes

    async def upload_artifact(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        kind: str = "artifact",
        creator: str = "mcp_tool",
        caption: str | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            raise ArtifactAuthError("AGENT_ARTIFACT_TOKEN não configurado no MCP server.")

        if len(file_bytes) > self._max_bytes:
            raise ArtifactSizeError(
                f"Arquivo excede o limite máximo de {self._max_bytes} bytes."
            )

        url = f"{self._base_url}/artifacts/upload"
        files = {"file": (filename, BytesIO(file_bytes), mime_type)}
        data: dict[str, Any] = {
            "filename": filename,
            "mime_type": mime_type,
            "kind": kind,
            "creator": creator,
        }
        if caption is not None:
            data["caption"] = caption

        max_retries = 3
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        url,
                        headers={"X-Agent-Token": self._token},
                        files=files,
                        data=data,
                    )
            except httpx.TimeoutException as exc:
                last_exc = ArtifactUploadError(
                    f"Timeout no upload (tentativa {attempt}/{max_retries}): {exc}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
                continue
            except httpx.RequestError as exc:
                last_exc = ArtifactUploadError(
                    f"Erro de conexão (tentativa {attempt}/{max_retries}): {exc}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
                continue

            if resp.status_code == 201:
                return resp.json()

            if resp.status_code == 401:
                raise ArtifactAuthError("Token inválido ou ausente.")

            if resp.status_code == 413:
                raise ArtifactSizeError("Arquivo excede o limite máximo.")

            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                last_exc = ArtifactServerError(
                    f"Erro do servidor (tentativa {attempt}/{max_retries}): HTTP {resp.status_code}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
                continue

            last_exc = ArtifactUploadError(
                f"Resposta inesperada HTTP {resp.status_code} (tentativa {attempt}/{max_retries})"
            )
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))

        raise ArtifactServerError(
            f"Upload falhou após {max_retries} tentativas. Último erro: {last_exc}"
        )
