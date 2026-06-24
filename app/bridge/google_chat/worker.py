from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
from typing import Any

from google.cloud import pubsub_v1
from google.oauth2 import service_account
from redis.asyncio import Redis as AsyncRedis

from app.bridge.google_chat.agent_adapter import AgentAdapter
from app.bridge.google_chat.chat_client import GoogleChatClient
from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)
from app.bridge.google_chat.dedupe_store import DedupeStore
from app.bridge.google_chat.media_downloader import GoogleChatMediaDownloader
from app.bridge.google_chat.parser import parse_google_chat_event
from app.bridge.google_chat.pubsub_subscriber import GoogleChatPubSubSubscriber
from app.infrastructure.locking.redis_lock import RedisDistributedLock

logger = logging.getLogger(__name__)

FAILURE_MESSAGE = (
    "Não consegui processar essa mensagem. "
    "A solicitação foi encerrada para evitar repetição automática."
)


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

        # Create async Redis client for deduplication lock
        redis_client = AsyncRedis.from_url(
            self.settings.redis_url, decode_responses=True
        )
        lock = RedisDistributedLock(redis_client, prefix="google_chat:dedupe_lock")
        self.dedupe_store = DedupeStore(settings=self.settings, lock=lock)

        self.media_downloader = GoogleChatMediaDownloader(settings=self.settings)

        # Background event loop for running async code from sync Pub/Sub callbacks
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._start_background_loop()

    def _start_background_loop(self) -> None:
        """Start a dedicated asyncio event loop in a background thread."""
        self._loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=_run_loop, daemon=True)
        self._loop_thread.start()

    def _stop_background_loop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=5)
        if self._loop is not None:
            self._loop.close()

    def _submit_async(self, coro) -> Any:
        """Submit a coroutine to the background loop and wait for result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

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
        """Called by Pub/Sub in a background thread. Dispatches to async."""
        self._submit_async(self._process_pubsub_message_async(message))

    async def _process_pubsub_message_async(
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

            dedupe_status = await self.dedupe_store.try_start(event)

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

            downloaded_images = self.media_downloader.download_images_from_event(event)

            if downloaded_images:
                logger.info(
                    "Imagens baixadas para OCR. count=%s total_bytes=%s",
                    len(downloaded_images),
                    sum(image.size_bytes for image in downloaded_images),
                )

            answer = self.agent_adapter.ask(
                event=event,
                images=downloaded_images,
            )

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

                await self.dedupe_store.mark_done(event)

                message.ack()
                logger.info("Dedupe marcado. ACK enviado.")
            else:
                await self.dedupe_store.release_processing(event)

                message.nack()
                logger.info("Modo teste: resposta não enviada. NACK enviado.")

        except Exception:
            logger.exception(
                "Erro ao processar mensagem Pub/Sub. payload=%s",
                json.dumps(payload, ensure_ascii=False) if payload else None,
            )

            await self._finish_after_error_async(
                pubsub_message=message,
                event=event,
                dedupe_started=dedupe_started,
                thinking_message_name=thinking_message_name,
            )

    async def _finish_after_error_async(
        self,
        pubsub_message: pubsub_v1.subscriber.message.Message,
        event,
        dedupe_started: bool,
        thinking_message_name: str | None,
    ) -> None:
        if event is not None and dedupe_started:
            try:
                await self.dedupe_store.mark_done(event)
                logger.info(
                    "Erro marcado como finalizado no dedupe. message_name=%s",
                    event.message_name,
                )
            except Exception:
                logger.exception("Falha ao marcar erro como finalizado no dedupe.")

        if self.send_to_chat:
            if thinking_message_name:
                try:
                    self.chat_client.update_text(
                        message_name=thinking_message_name,
                        text=FAILURE_MESSAGE,
                    )

                    logger.info(
                        "Mensagem de espera atualizada com falha controlada. message_name=%s",
                        thinking_message_name,
                    )
                except Exception:
                    logger.exception(
                        "Falha ao atualizar mensagem de espera após erro."
                    )

            pubsub_message.ack()
            logger.info("ACK enviado após erro para evitar loop.")
            return

        if event is not None and dedupe_started:
            try:
                await self.dedupe_store.release_processing(event)
            except Exception:
                logger.exception("Falha ao liberar processing no dedupe.")

        pubsub_message.nack()
        logger.info("Modo teste: NACK enviado após erro.")


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
