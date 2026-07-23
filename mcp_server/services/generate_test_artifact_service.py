from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from clients.artifact_client import ArtifactClient

logger = logging.getLogger("mcp_server.generate_test_artifact")


async def generate_test_artifact(
    filename: str = "test_artifact.txt",
    content: str | None = None,
    mime_type: str = "text/plain",
    caption: str | None = None,
) -> str:
    from core.config import settings

    if content is None:
        content = (
            f"Test artifact generated at {datetime.now(tz=timezone.utc).isoformat()}\n"
        )

    client = ArtifactClient(
        base_url=settings.AGENT_API_BASE_URL,
        token=settings.AGENT_ARTIFACT_TOKEN,
        timeout=settings.AGENT_ARTIFACT_UPLOAD_TIMEOUT_SECONDS,
        max_bytes=settings.AGENT_ARTIFACT_MAX_UPLOAD_BYTES,
    )

    try:
        attachment = await client.upload_artifact(
            file_bytes=content.encode("utf-8"),
            filename=filename,
            mime_type=mime_type,
            caption=caption or f"Arquivo gerado: {filename}",
        )

        return json.dumps(
            {
                "type": "agent_artifact_result",
                "answer": f"Arquivo '{filename}' gerado e enviado com sucesso.",
                "attachments": [attachment],
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("generate_test_artifact failed: %s", exc)
        return json.dumps(
            {
                "type": "agent_artifact_result",
                "answer": f"Não foi possível gerar o arquivo. Erro: {exc}",
                "attachments": [],
            },
            ensure_ascii=False,
        )
