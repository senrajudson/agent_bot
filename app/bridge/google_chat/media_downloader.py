from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)
from app.bridge.google_chat.models import (
    GoogleChatAttachment,
    GoogleChatIncomingMessage,
)

logger = logging.getLogger(__name__)


DEFAULT_ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


@dataclass(slots=True)
class DownloadedGoogleChatImage:
    filename: str
    content_type: str
    size_bytes: int
    base64_data: str
    attachment_name: str
    resource_name: str


class GoogleChatMediaDownloader:
    def __init__(
        self,
        settings: GoogleChatBridgeSettings | None = None,
        max_images: int = 4,
        max_image_bytes: int = 10 * 1024 * 1024,
        allowed_image_types: set[str] | None = None,
    ):
        self.settings = settings or get_google_chat_bridge_settings()
        self.settings.validate_google_chat_config()

        self.max_images = max_images
        self.max_image_bytes = max_image_bytes
        self.allowed_image_types = allowed_image_types or DEFAULT_ALLOWED_IMAGE_TYPES

        self._service = None

    @property
    def service(self):
        if self._service is None:
            credentials = service_account.Credentials.from_service_account_file(
                str(self.settings.service_account_path),
                scopes=self.settings.google_chat_scopes,
            )

            self._service = build(
                "chat",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )

        return self._service

    def download_images_from_event(
        self,
        event: GoogleChatIncomingMessage,
    ) -> list[DownloadedGoogleChatImage]:
        images: list[DownloadedGoogleChatImage] = []

        for attachment in event.attachments:
            if len(images) >= self.max_images:
                logger.warning(
                    "Limite de imagens atingido. max_images=%s message_name=%s",
                    self.max_images,
                    event.message_name,
                )
                break

            if not self._should_download_attachment(attachment):
                logger.info(
                    "Attachment ignorado. name=%s content_type=%s source=%s has_resource=%s",
                    attachment.name,
                    attachment.content_type,
                    attachment.source,
                    bool(attachment.resource_name),
                )
                continue

            image = self.download_image_attachment(attachment)
            images.append(image)

        return images

    def download_image_attachment(
        self,
        attachment: GoogleChatAttachment,
    ) -> DownloadedGoogleChatImage:
        if not attachment.resource_name:
            raise ValueError("Attachment sem attachmentDataRef.resourceName.")

        try:
            request = self.service.media().download_media(
                resourceName=attachment.resource_name,
            )

            output = io.BytesIO()
            downloader = MediaIoBaseDownload(output, request)

            done = False

            while not done:
                _, done = downloader.next_chunk()

                current_size = output.tell()

                if current_size > self.max_image_bytes:
                    raise RuntimeError(
                        "Imagem excedeu o limite configurado. "
                        f"filename={attachment.content_name} "
                        f"size_bytes={current_size} "
                        f"max_image_bytes={self.max_image_bytes}"
                    )

            image_bytes = output.getvalue()

        except HttpError as exc:
            status = getattr(exc.resp, "status", "unknown")

            try:
                content = exc.content.decode("utf-8", errors="replace")
            except Exception:
                content = str(exc)

            logger.exception(
                "Falha ao baixar attachment do Google Chat. "
                "attachment_name=%s resource_name=%s status=%s content=%s",
                attachment.name,
                attachment.resource_name,
                status,
                content,
            )

            raise RuntimeError(
                "Falha ao baixar attachment do Google Chat. "
                f"Status: {status}. Detalhe: {content}"
            ) from exc

        base64_data = base64.b64encode(image_bytes).decode("ascii")

        return DownloadedGoogleChatImage(
            filename=attachment.content_name or "image",
            content_type=attachment.content_type,
            size_bytes=len(image_bytes),
            base64_data=base64_data,
            attachment_name=attachment.name,
            resource_name=attachment.resource_name,
        )

    def _should_download_attachment(
        self,
        attachment: GoogleChatAttachment,
    ) -> bool:
        content_type = attachment.content_type.lower().strip()

        if not attachment.can_download_with_chat_api:
            return False

        if content_type not in self.allowed_image_types:
            return False

        return True