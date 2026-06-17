from __future__ import annotations

import argparse
import base64
import json
import logging
import threading
from typing import Any

from google.cloud import pubsub_v1
from google.oauth2 import service_account

from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)

logger = logging.getLogger(__name__)


class GoogleChatPubSubSubscriber:
    def __init__(self, settings: GoogleChatBridgeSettings | None = None):
        self.settings = settings or get_google_chat_bridge_settings()
        self.settings.validate_google_chat_config()

        self.credentials = service_account.Credentials.from_service_account_file(
            str(self.settings.service_account_path),
        )

        self.subscriber = pubsub_v1.SubscriberClient(
            credentials=self.credentials,
        )

        self.subscription_path = self.settings.google_chat_subscription

    def listen_once(
        self,
        timeout_seconds: int = 60,
        ack: bool = False,
    ) -> dict[str, Any] | None:
        finished = threading.Event()
        received_payload: dict[str, Any] | None = None

        def callback(message: pubsub_v1.subscriber.message.Message) -> None:
            nonlocal received_payload

            try:
                payload = self.decode_message(message)
                received_payload = payload

                print("\nMensagem recebida do Pub/Sub:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))

                if ack:
                    message.ack()
                    print("\nACK enviado. A mensagem foi removida da subscription.")
                else:
                    message.nack()
                    print("\nNACK enviado. A mensagem poderá ser entregue novamente.")

            except Exception:
                logger.exception("Erro ao processar mensagem recebida do Pub/Sub.")
                message.nack()

            finally:
                finished.set()

        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=callback,
        )

        print(f"Aguardando mensagem em: {self.subscription_path}")
        print(f"Timeout: {timeout_seconds}s")
        print(f"ACK habilitado: {ack}")

        try:
            finished.wait(timeout=timeout_seconds)
            streaming_pull_future.cancel()

            try:
                streaming_pull_future.result(timeout=5)
            except Exception:
                pass

            return received_payload

        finally:
            self.subscriber.close()

    @staticmethod
    def decode_message(
        message: pubsub_v1.subscriber.message.Message,
    ) -> dict[str, Any]:
        raw_data = message.data or b""

        decoded_text = raw_data.decode("utf-8", errors="replace")

        payload: dict[str, Any]

        try:
            payload = json.loads(decoded_text)
        except json.JSONDecodeError:
            payload = {
                "rawText": decoded_text,
            }

        return {
            "pubsubMessageId": message.message_id,
            "publishTime": str(message.publish_time),
            "attributes": dict(message.attributes or {}),
            "payload": payload,
            "rawDataBase64": base64.b64encode(raw_data).decode("ascii"),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lê uma mensagem do Google Pub/Sub usada pelo Google Chat."
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Tempo máximo aguardando mensagem, em segundos.",
    )

    parser.add_argument(
        "--ack",
        action="store_true",
        help="Confirma a mensagem no Pub/Sub. Sem isso, envia NACK.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    subscriber = GoogleChatPubSubSubscriber()
    payload = subscriber.listen_once(
        timeout_seconds=args.timeout,
        ack=args.ack,
    )

    if payload is None:
        print("\nNenhuma mensagem recebida no tempo limite.")


if __name__ == "__main__":
    main()