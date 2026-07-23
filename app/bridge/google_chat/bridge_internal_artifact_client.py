from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx
from tenacity import (
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class BridgeArtifactClientError(Exception):
    pass


class BridgeArtifactNotFound(BridgeArtifactClientError):
    pass


class BridgeArtifactExpired(BridgeArtifactClientError):
    pass


class BridgeArtifactClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        max_bytes: int = 26214400,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._max_bytes = max_bytes

    def get_metadata(self, artifact_id: str) -> dict:
        url = f"{self._base_url}/{artifact_id}/metadata"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url, headers={"X-Agent-Token": self._token})
        if resp.status_code == 404:
            raise BridgeArtifactNotFound(f"Artifact {artifact_id} não encontrado.")
        if resp.status_code == 410:
            raise BridgeArtifactExpired(f"Artifact {artifact_id} expirado.")
        resp.raise_for_status()
        return resp.json()

    def download_to_temp(self, artifact_id: str, filename: str) -> Path:
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                return self._download_once(artifact_id, filename)
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                logger.warning(
                    "artifact_download_retry: id=%s attempt=%d/3 error=%s",
                    artifact_id, attempt, exc,
                )
                last_exc = exc
                if attempt < 3:
                    import asyncio
                    asyncio.run(asyncio.sleep(2 ** (attempt - 1)))
            except BridgeArtifactClientError:
                raise
        raise BridgeArtifactClientError(
            f"Download de {artifact_id} falhou após 3 tentativas. Último erro: {last_exc}"
        )

    def _download_once(self, artifact_id: str, filename: str) -> Path:
        url = f"{self._base_url}/{artifact_id}/download"
        with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
            with client.stream("GET", url, headers={"X-Agent-Token": self._token}) as resp:
                if resp.status_code == 404:
                    raise BridgeArtifactNotFound(
                        f"Artifact {artifact_id} não encontrado."
                    )
                if resp.status_code == 410:
                    raise BridgeArtifactExpired(
                        f"Artifact {artifact_id} expirado."
                    )
                if resp.status_code in (401, 403):
                    raise BridgeArtifactClientError(
                        f"Autenticação inválida para artifact {artifact_id}."
                    )
                if resp.status_code == 413:
                    raise BridgeArtifactClientError(
                        f"Artifact {artifact_id} excede o limite de download."
                    )
                resp.raise_for_status()
                tmp = NamedTemporaryFile(delete=False, suffix=filename)
                total = 0
                try:
                    for chunk in resp.iter_bytes(65536):
                        total += len(chunk)
                        if total > self._max_bytes:
                            raise BridgeArtifactClientError(
                                f"Download excedeu o limite de {self._max_bytes} bytes."
                            )
                        tmp.write(chunk)
                    tmp.close()
                    return Path(tmp.name)
                except BaseException:
                    Path(tmp.name).unlink(missing_ok=True)
                    raise
