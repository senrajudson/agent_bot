from __future__ import annotations

import argparse
import json
import logging
import threading
from typing import Any

from google.cloud import pubsub_v1
from google.oauth2 import service_account

from app.bridge.google_chat.agent_adapter import AgentAdapter
from app.bridge.google_chat.chat_client import GoogleChatClient
from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)
from app.bridge.google_chat.dedupe_store import DedupeStore
from app.bridge.google_chat.parser import parse_google_chat_event
from app.bridge.google_chat.pubsub_subscriber import GoogleChatPubSubSubscriber

logger = logging.getLogger(__name__)


class GoogleChatBridgeWorker:
    def __init__(
        self,
        settings: GoogleChatBridgeSettings | None = None,
        send_to_chat: bool = False,
    ):
        self.settings = settings or get_google_chat_bridge_settings()
        self.settings.validate_google_chat_config()

        self.send_to_chat = send_to_chat

        self.credentials = service_account.Credentials.from_service_account_file(
            str(self.settings.service_account_path),
        )

        self.subscriber = pubsub_v1.SubscriberClient(
            credentials=self.credentials,
        )

        self.subscription_path = self.settings.google_chat_subscription

        self.agent_adapter = AgentAdapter(settings=self.settings)
        self.chat_client = GoogleChatClient(settings=self.settings)
        self.dedupe_store = DedupeStore(settings=self.settings)

    def run_once(self, timeout_seconds: int = 120) -> None:
        finished = threading.Event()

        def callback(message: pubsub_v1.subscriber.message.Message) -> None:
            try:
                self.process_pubsub_message(message)
            finally:
                finished.set()

        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=callback,
        )

        logger.info("Aguardando uma mensagem em: %s", self.subscription_path)
        logger.info("Timeout: %ss", timeout_seconds)
        logger.info("Enviar resposta para o Chat: %s", self.send_to_chat)

        try:
            finished.wait(timeout=timeout_seconds)

            streaming_pull_future.cancel()

            try:
                streaming_pull_future.result(timeout=5)
            except Exception:
                pass

            if not finished.is_set():
                logger.warning("Nenhuma mensagem recebida no tempo limite.")

        finally:
            self.subscriber.close()

    def run_forever(self) -> None:
        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=self.process_pubsub_message,
        )

        logger.info("Worker iniciado.")
        logger.info("Subscription: %s", self.subscription_path)
        logger.info("Enviar resposta para o Chat: %s", self.send_to_chat)

        try:
            streaming_pull_future.result()
        except KeyboardInterrupt:
            logger.info("Encerrando worker por KeyboardInterrupt.")
            streaming_pull_future.cancel()

            try:
                streaming_pull_future.result(timeout=5)
            except Exception:
                pass
        finally:
            self.subscriber.close()

    def process_pubsub_message(
        self,
        message: pubsub_v1.subscriber.message.Message,
    ) -> None:
        payload: dict[str, Any] | None = None
        event = None
        dedupe_started = False
        thinking_message_name: str | None = None

        try:
            payload = GoogleChatPubSubSubscriber.decode_message(message)
            event = parse_google_chat_event(payload)

            logger.info(
                "Evento recebido: %s",
                json.dumps(event.to_log_dict(), ensure_ascii=False),
            )

            if not event.can_process:
                logger.info("Evento ignorado. can_process=false.")

                if self.send_to_chat:
                    message.ack()
                    logger.info("ACK enviado para evento ignorado.")
                else:
                    message.nack()
                    logger.info("NACK enviado em modo teste.")

                return

            dedupe_status = self.dedupe_store.try_start(event)

            if dedupe_status != "started":
                logger.info(
                    "Mensagem duplicada detectada. status=%s message_name=%s",
                    dedupe_status,
                    event.message_name,
                )

                if self.send_to_chat:
                    message.ack()
                    logger.info("ACK enviado para duplicata.")
                else:
                    message.nack()
                    logger.info("NACK enviado para duplicata em modo teste.")

                return

            dedupe_started = True

            if self.send_to_chat and self.settings.google_chat_send_thinking_message:
                thinking_message = self.chat_client.send_thinking(
                    space_name=event.space_name,
                    thread_name=None,
                )

                thinking_message_name = str(thinking_message.get("name", "") or "")

                logger.info(
                    "Mensagem de espera enviada. thinking_message_name=%s original_message_name=%s",
                    thinking_message_name,
                    event.message_name,
                )

            answer = self.agent_adapter.ask(event)

            logger.info("Resposta do agente:")
            logger.info("\n%s", answer)

            if self.send_to_chat:
                if thinking_message_name:
                    self.chat_client.update_text(
                        message_name=thinking_message_name,
                        text=answer,
                    )

                    logger.info(
                        "Mensagem de espera atualizada com resposta final. message_name=%s",
                        thinking_message_name,
                    )
                else:
                    self.chat_client.send_text(
                        space_name=event.space_name,
                        thread_name=None,
                        text=answer,
                    )

                    logger.info("Resposta enviada como nova mensagem.")

                self.dedupe_store.mark_done(event)

                message.ack()
                logger.info("Dedupe marcado. ACK enviado.")
            else:
                self.dedupe_store.release_processing(event)

                message.nack()
                logger.info("Modo teste: resposta não enviada. NACK enviado.")

        except Exception:
            logger.exception(
                "Erro ao processar mensagem Pub/Sub. payload=%s",
                json.dumps(payload, ensure_ascii=False) if payload else None,
            )

            if event is not None and dedupe_started:
                self.dedupe_store.release_processing(event)

            message.nack()
            logger.info("NACK enviado após erro.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Worker da bridge Google Chat -> Pub/Sub -> Agente -> Google Chat."
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Processa apenas uma mensagem e encerra.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout em segundos quando usado com --once.",
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help="Envia a resposta para o Google Chat e confirma ACK em caso de sucesso.",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nível de log.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    worker = GoogleChatBridgeWorker(
        send_to_chat=args.send,
    )

    if args.once:
        worker.run_once(timeout_seconds=args.timeout)
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()