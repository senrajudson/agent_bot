"""
Pub/Sub worker — bridges Pub/Sub messages to the orchestrator.

Flow per incoming message:
  1. Parse + validate IncomingMessage
  2. Dedup check via Redis (skip if request_id already processed)
  3. Build ChatRequest, call process_message()
  4. Build OutgoingMessage from ChatResponse
  5. Publish to outgoing topic
  6. Mark request_id as processed
  7. Ack Pub/Sub message

On any error:
  - Publish an error OutgoingMessage so the user isn't left hanging
  - Nack the Pub/Sub message for retry
"""

import json
import logging
from typing import Any

from google.cloud.pubsub_v1.subscriber.message import Message

from app.agent.orchestrator import process_message
from app.clients.redis_client import get_redis_client
from app.core.config import settings
from app.pubsub.publisher import AgentPublisher
from app.pubsub.schemas import IncomingMessage, OutgoingMessage
from app.schemas.chat import ChatRequest


logger = logging.getLogger(__name__)

DEDUP_KEY_PREFIX = "pubsub:processed"


def _dedup_key(request_id: str) -> str:
    return f"{DEDUP_KEY_PREFIX}:{request_id}"


async def is_processed(request_id: str) -> bool:
    redis = get_redis_client()
    try:
        return bool(await redis.exists(_dedup_key(request_id)))
    except Exception as e:
        logger.warning("Redis dedup check failed (treating as not processed): %s", e)
        return False


async def mark_processed(request_id: str) -> None:
    redis = get_redis_client()
    try:
        await redis.set(
            _dedup_key(request_id),
            "1",
            ex=settings.PUBSUB_DEDUP_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning("Redis dedup mark failed: %s", e)


def _parse_incoming(message: Message) -> IncomingMessage:
    raw = message.data
    if not raw:
        raise ValueError("Empty Pub/Sub message data")

    payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
    return IncomingMessage.model_validate(payload)


def _build_error_outgoing(request_id: str, error: str) -> OutgoingMessage:
    return OutgoingMessage(
        request_id=request_id,
        type="error",
        content=(
            "Não consegui processar sua mensagem agora. "
            "Tente novamente em instantes."
        ),
        error=error,
    )


async def _publish_error_and_ack(
    publisher: AgentPublisher,
    request_id: str,
    error: str,
    message: Message,
) -> None:
    try:
        await publisher.publish(_build_error_outgoing(request_id, error))
    except Exception:
        logger.exception("Failed to publish error outgoing message for request_id=%s", request_id)
    try:
        message.ack()
    except Exception:
        logger.exception("Failed to ack message after error")


async def handle_incoming(
    message: Message,
    publisher: AgentPublisher,
) -> None:
    """
    Main handler for Pub/Sub messages. Always acks or nacks the message.
    """

    try:
        incoming = _parse_incoming(message)
    except Exception as e:
        logger.warning("Malformed incoming message, dropping: %s", e)
        message.ack()
        return

    request_id = incoming.request_id
    logger.info(
        "Handling incoming message request_id=%s user_id=%s conversation_id=%s",
        request_id,
        incoming.user_id,
        incoming.conversation_id,
    )

    if await is_processed(request_id):
        logger.info("Duplicate request_id=%s, skipping LLM call but acking", request_id)
        message.ack()
        return

    chat_request = ChatRequest(
        message=incoming.message,
        user_id=incoming.user_id,
        conversation_id=incoming.conversation_id,
        images=incoming.images or [],
    )

    try:
        response = await process_message(chat_request)

        outgoing = OutgoingMessage(
            request_id=request_id,
            type="response" if response.ok else "error",
            content=response.output or "Não consegui gerar uma resposta.",
            categoria=response.categoria,
            next_action=response.next_action,
            has_image=response.has_image,
            tags_encontradas=response.tags_encontradas or [],
            agent_trace=response.agent_trace or [],
            error=response.answer_generation_error,
        )

        try:
            await publisher.publish(outgoing)
        except Exception as pub_err:
            logger.exception("Failed to publish outgoing message for request_id=%s", request_id)
            message.nack()
            return

        await mark_processed(request_id)
        message.ack()
        logger.info("Handled request_id=%s categoria=%s", request_id, response.categoria)

    except Exception as e:
        logger.exception("Handler error for request_id=%s", request_id)
        await _publish_error_and_ack(
            publisher=publisher,
            request_id=request_id,
            error=str(e),
            message=message,
        )
