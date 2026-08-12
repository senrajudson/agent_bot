from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from mcp_server.clients.google_drive_client import (
    GoogleDriveClient,
    DriveCsvAuthError,
    DriveCsvError,
    DriveCsvQuotaError,
)

from mcp_server.services.delivery.exceptions import ArtifactDeliveryError, DriveConfigError

logger = logging.getLogger("mcp_server.drive_publisher")


@dataclass(frozen=True)
class PublishedArtifact:
    name: str
    mime_type: str
    size_bytes: int
    view_url: str


class DrivePublisher(Protocol):
    def publish(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        app_properties: dict[str, str] | None = None,
    ) -> PublishedArtifact: ...


class DefaultDrivePublisher:
    def __init__(self, client: GoogleDriveClient) -> None:
        self._client = client

    def publish(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        app_properties: dict[str, str] | None = None,
    ) -> PublishedArtifact:
        try:
            uploaded = self._client.upload_file(
                filename=filename,
                file_bytes=file_bytes,
                mime_type=mime_type,
                app_properties=app_properties or {},
            )
        except DriveCsvAuthError as exc:
            raise DriveConfigError(str(exc)) from exc
        except DriveCsvQuotaError as exc:
            raise ArtifactDeliveryError(str(exc)) from exc
        except DriveCsvError as exc:
            raise ArtifactDeliveryError(str(exc)) from exc

        logger.info(
            "publish: filename=%s size=%d",
            uploaded.name,
            uploaded.size,
        )

        return PublishedArtifact(
            name=uploaded.name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size,
            view_url=uploaded.web_view_link,
        )
