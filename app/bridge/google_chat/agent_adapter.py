from __future__ import annotations

import logging
from typing import Any

import httpx

from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)
from app.bridge.google_chat.media_downloader import DownloadedGoogleChatImage
from app.bridge.google_chat.models import GoogleChatIncomingMessage
from app.schemas.chat import ChatAttachment

logger = logging.getLogger(__name__)


class AgentAdapter:
    def __init__(
        self,
        settings: GoogleChatBridgeSettings | None = None,
        timeout_seconds: float = 180.0,
    ):
        self.settings = settings or get_google_chat_bridge_settings()
        self.settings.validate_google_chat_config()
        self.timeout_seconds = timeout_seconds

    def ask(
        self,
        event: GoogleChatIncomingMessage,
        images: list[DownloadedGoogleChatImage] | None = None,
    ) -> str:
        if not event.can_process:
            raise ValueError(
                "Evento não pode ser processado pelo agente. "
                f"Dados: {event.to_log_dict()}"
            )

        images = images or []

        payload = self._build_agent_payload(
            event=event,
            images=images,
        )

        logger.info(
            "Enviando mensagem para o agente. url=%s message_name=%s space_name=%s images=%s",
            self.settings.agent_internal_url,
            event.message_name,
            event.space_name,
            len(images),
        )

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    self.settings.agent_internal_url,
                    json=payload,
                )

            response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            content = exc.response.text if exc.response is not None else ""

            logger.exception(
                "Agente retornou erro HTTP. status=%s content=%s",
                status_code,
                content,
            )

            raise RuntimeError(
                "Agente retornou erro HTTP. "
                f"Status: {status_code}. "
                f"Detalhe: {content}"
            ) from exc

        except httpx.RequestError as exc:
            logger.exception(
                "Falha de conexão ao chamar o agente. url=%s",
                self.settings.agent_internal_url,
            )

            raise RuntimeError(
                "Falha de conexão ao chamar o agente. "
                f"URL: {self.settings.agent_internal_url}. "
                f"Detalhe: {exc}"
            ) from exc

        answer = self._extract_answer(response)

        if not answer:
            answer = "Não consegui gerar uma resposta para essa mensagem."

        return answer.strip()

    def _build_agent_payload(
        self,
        event: GoogleChatIncomingMessage,
        images: list[DownloadedGoogleChatImage],
    ) -> dict[str, Any]:
        user_id = event.user.name or event.user.email or "google-chat-user"

        message = event.clean_text

        if images and not message:
            message = (
                "Faça OCR da imagem enviada e responda com base no texto extraído. "
                "Se a imagem contiver apenas uma tag, retorne a tag identificada."
            )

        payload: dict[str, Any] = {
            "message": message,
            "user_id": user_id,
        }

        if images:
            payload["images"] = [
                {
                    "image_base64": image.base64_data,
                    "mime_type": image.content_type or "image/png",
                    "file_name": image.filename,
                    "image_index": index,
                }
                for index, image in enumerate(images)
            ]

        return payload

    @staticmethod
    def _extract_answer(response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "")

        if "application/json" not in content_type.lower():
            return response.text.strip()

        try:
            data = response.json()
        except ValueError:
            return response.text.strip()

        return AgentAdapter._extract_text_from_json(data)

    @staticmethod
    def _extract_text_from_json(data: Any) -> str:
        if isinstance(data, str):
            return data.strip()

        if not isinstance(data, dict):
            return str(data).strip() if data is not None else ""

        possible_keys = (
            "response",
            "answer",
            "message",
            "content",
            "text",
            "output",
            "result",
            "reply",
            "assistant_message",
            "final_answer",
        )

        for key in possible_keys:
            value = data.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

        data_value = data.get("data")

        if isinstance(data_value, dict):
            nested = AgentAdapter._extract_text_from_json(data_value)

            if nested:
                return nested

        if isinstance(data_value, str) and data_value.strip():
            return data_value.strip()

        return str(data).strip()