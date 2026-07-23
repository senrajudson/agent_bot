from __future__ import annotations

import logging
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)

logger = logging.getLogger(__name__)


SAFE_CHAT_MESSAGE_BYTES = 30000


class GoogleChatClient:
    def __init__(self, settings: GoogleChatBridgeSettings | None = None):
        self.settings = settings or get_google_chat_bridge_settings()
        self.settings.validate_google_chat_config()
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

    def send_text(
        self,
        space_name: str,
        text: str,
        thread_name: str | None = None,
    ) -> dict[str, Any]:
        if not space_name:
            raise ValueError("space_name não informado.")

        if not space_name.startswith("spaces/"):
            raise ValueError(
                f"space_name inválido: {space_name}. "
                "O valor esperado começa com 'spaces/'."
            )

        message_text = self._normalize_text(text)

        body: dict[str, Any] = {
            "text": message_text,
        }

        request_params: dict[str, Any] = {
            "parent": space_name,
            "body": body,
        }

        if thread_name:
            body["thread"] = {
                "name": thread_name,
            }
            request_params["messageReplyOption"] = (
                "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"
            )

        try:
            result = (
                self.service
                .spaces()
                .messages()
                .create(**request_params)
                .execute()
            )

            return result

        except HttpError as exc:
            status = getattr(exc.resp, "status", "unknown")

            try:
                content = exc.content.decode("utf-8", errors="replace")
            except Exception:
                content = str(exc)

            logger.exception(
                "Falha ao enviar mensagem para o Google Chat. "
                "space_name=%s thread_name=%s status=%s content=%s",
                space_name,
                thread_name,
                status,
                content,
            )

            raise RuntimeError(
                "Falha ao enviar mensagem para o Google Chat. "
                f"Status: {status}. Detalhe: {content}"
            ) from exc

    def update_text(
        self,
        message_name: str,
        text: str,
    ) -> dict[str, Any]:
        if not message_name:
            raise ValueError("message_name não informado.")

        if not message_name.startswith("spaces/"):
            raise ValueError(
                f"message_name inválido: {message_name}. "
                "O valor esperado começa com 'spaces/'."
            )

        message_text = self._normalize_text(text)

        body: dict[str, Any] = {
            "text": message_text,
        }

        try:
            result = (
                self.service
                .spaces()
                .messages()
                .patch(
                    name=message_name,
                    updateMask="text",
                    body=body,
                )
                .execute()
            )

            return result

        except HttpError as exc:
            status = getattr(exc.resp, "status", "unknown")

            try:
                content = exc.content.decode("utf-8", errors="replace")
            except Exception:
                content = str(exc)

            logger.exception(
                "Falha ao atualizar mensagem no Google Chat. "
                "message_name=%s status=%s content=%s",
                message_name,
                status,
                content,
            )

            raise RuntimeError(
                "Falha ao atualizar mensagem no Google Chat. "
                f"Status: {status}. Detalhe: {content}"
            ) from exc

    def send_attachment(
        self,
        space_name: str,
        file_path: str,
        mime_type: str,
        filename: str,
        caption: str | None = None,
        thread_name: str | None = None,
        sender_email: str | None = None,
    ) -> dict[str, Any]:
        from pathlib import Path

        path = Path(file_path).resolve()
        if not path.is_file():
            raise ValueError(f"Arquivo não encontrado: {file_path}")

        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(
            filename=str(path),
            mimetype=mime_type,
            resumable=True,
        )

        body: dict[str, Any] = {
            "text": caption or filename,
        }
        if thread_name:
            body["thread"] = {"name": thread_name}

        try:
            upload_response = (
                self.service.spaces()
                .messages()
                .create(
                    parent=space_name,
                    body=body,
                    media_body=media,
                )
                .execute()
            )
            return upload_response
        except Exception as exc:
            logger.exception(
                "Falha ao enviar attachment. path=%s mime=%s",
                file_path,
                mime_type,
            )
            raise RuntimeError(
                f"Falha ao enviar attachment: {exc}" if not isinstance(exc, RuntimeError) else str(exc)
            ) from exc

    def send_thinking(
        self,
        space_name: str,
        thread_name: str | None = None,
    ) -> dict[str, Any]:
        return self.send_text(
            space_name=space_name,
            text=self.settings.google_chat_thinking_text,
            thread_name=thread_name,
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        if text is None:
            text = ""

        normalized = str(text).strip()

        if not normalized:
            normalized = "Mensagem vazia."

        return GoogleChatClient._truncate_utf8(
            text=normalized,
            max_bytes=SAFE_CHAT_MESSAGE_BYTES,
        )

    @staticmethod
    def _truncate_utf8(text: str, max_bytes: int) -> str:
        encoded = text.encode("utf-8")

        if len(encoded) <= max_bytes:
            return text

        suffix = "\n\n[Mensagem truncada por limite do Google Chat.]"
        suffix_bytes = suffix.encode("utf-8")

        available_bytes = max_bytes - len(suffix_bytes)

        if available_bytes <= 0:
            return "[Mensagem truncada.]"

        truncated = encoded[:available_bytes]

        while truncated:
            try:
                return truncated.decode("utf-8") + suffix
            except UnicodeDecodeError:
                truncated = truncated[:-1]

        return "[Mensagem truncada.]"