"""Characterization tests for Worker._process_pubsub_message_async (TASK-008).

Locks down the worker behavior:
- send_to_chat=True → ack + mark_done + chat_client.send/update
- send_to_chat=False → nack + release_processing
- can_process=False → ack/nack without agent call
- Duplicate message → ack/nack without agent call
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pubsub_message(data=b'{"message": "hello"}', message_id="msg-1"):
    msg = MagicMock()
    msg.data = data
    msg.message_id = message_id
    msg.publish_time = "2026-01-01T00:00:00Z"
    msg.attributes = {}
    msg.ack = MagicMock()
    msg.nack = MagicMock()
    return msg


def _make_worker(send_to_chat=True):
    """Build a GoogleChatBridgeWorker with all dependencies mocked."""
    with patch("app.bridge.google_chat.worker.service_account.Credentials.from_service_account_file"):
        with patch("app.bridge.google_chat.worker.pubsub_v1.SubscriberClient"):
            from app.bridge.google_chat.config import GoogleChatBridgeSettings
            settings = MagicMock()
            # Set all required attributes that __init__ accesses
            settings.google_chat_subscription = "projects/p/subscriptions/s"
            settings.service_account_path = "/fake/path.json"
            settings.google_chat_send_thinking_message = False
            settings.google_chat_thinking_text = "Um momento..."
            settings.google_chat_dedupe_ttl_seconds = 86400
            settings.redis_url = "redis://localhost:6379"
            settings.send_to_chat = send_to_chat
            settings.enable_chat_attachments = False
            settings.validate_google_chat_config = MagicMock()

            from app.bridge.google_chat.worker import GoogleChatBridgeWorker
            worker = GoogleChatBridgeWorker(settings=settings, send_to_chat=send_to_chat)

            # Mock all sub-components
            worker.chat_client = MagicMock()
            worker.chat_client.send_text = MagicMock()
            worker.chat_client.send_thinking = MagicMock(return_value={"name": "thinking-msg"})
            worker.chat_client.update_text = MagicMock()

            worker.agent_adapter = MagicMock()
            worker.agent_adapter.ask = MagicMock(return_value=("resposta do agente", []))

            worker.media_downloader = MagicMock()
            worker.media_downloader.download_images_from_event = MagicMock(return_value=[])

            worker.dedupe_store = MagicMock()
            worker.dedupe_store.try_start = AsyncMock(return_value="started")
            worker.dedupe_store.mark_done = AsyncMock()
            worker.dedupe_store.release_processing = AsyncMock()

            return worker


def _patch_parse_event(return_can_process=True):
    """Patch parse_google_chat_event to return a controllable event."""
    mock_event = MagicMock()
    mock_event.can_process = return_can_process
    mock_event.space_name = "spaces/abc"
    mock_event.message_name = "spaces/abc/messages/1"
    mock_event.to_log_dict = MagicMock(return_value={})
    return patch(
        "app.bridge.google_chat.worker.parse_google_chat_event",
        return_value=mock_event,
    )


class TestWorkerSendToChatTrue:
    """W-1: send_to_chat=True → ack + mark_done + send."""

    @pytest.mark.asyncio
    async def test_normal_message_acks_and_sends(self):
        worker = _make_worker(send_to_chat=True)

        with _patch_parse_event(return_can_process=True):
            mock_event = worker.dedupe_store.try_start.return_value
            msg = _make_pubsub_message()

            await worker._process_pubsub_message_async(msg)

        worker.dedupe_store.try_start.assert_awaited_once()
        worker.agent_adapter.ask.assert_called_once()
        worker.chat_client.send_text.assert_called_once()
        worker.dedupe_store.mark_done.assert_awaited_once()
        msg.ack.assert_called_once()
        msg.nack.assert_not_called()


class TestWorkerSendToChatFalse:
    """W-2: send_to_chat=False → nack + release_processing."""

    @pytest.mark.asyncio
    async def test_normal_message_nacks_and_releases(self):
        worker = _make_worker(send_to_chat=False)

        with _patch_parse_event(return_can_process=True):
            msg = _make_pubsub_message()

            await worker._process_pubsub_message_async(msg)

        worker.agent_adapter.ask.assert_called_once()
        worker.chat_client.send_text.assert_not_called()
        worker.dedupe_store.release_processing.assert_awaited_once()
        msg.nack.assert_called_once()
        msg.ack.assert_not_called()


class TestWorkerCanNotProcess:
    """W-3: can_process=False → ack/nack without agent call."""

    @pytest.mark.asyncio
    async def test_not_processable_send_true(self):
        worker = _make_worker(send_to_chat=True)

        with _patch_parse_event(return_can_process=False):
            msg = _make_pubsub_message()

            await worker._process_pubsub_message_async(msg)

        worker.agent_adapter.ask.assert_not_called()
        msg.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_processable_send_false(self):
        worker = _make_worker(send_to_chat=False)

        with _patch_parse_event(return_can_process=False):
            msg = _make_pubsub_message()

            await worker._process_pubsub_message_async(msg)

        worker.agent_adapter.ask.assert_not_called()
        msg.nack.assert_called_once()


class TestWorkerDuplicate:
    """W-4: Duplicate message → ack/nack without agent call."""

    @pytest.mark.asyncio
    async def test_duplicate_send_true(self):
        worker = _make_worker(send_to_chat=True)
        worker.dedupe_store.try_start = AsyncMock(return_value="duplicate_processing")

        with _patch_parse_event(return_can_process=True):
            msg = _make_pubsub_message()

            await worker._process_pubsub_message_async(msg)

        worker.agent_adapter.ask.assert_not_called()
        msg.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_send_false(self):
        worker = _make_worker(send_to_chat=False)
        worker.dedupe_store.try_start = AsyncMock(return_value="duplicate_processing")

        with _patch_parse_event(return_can_process=True):
            msg = _make_pubsub_message()

            await worker._process_pubsub_message_async(msg)

        worker.agent_adapter.ask.assert_not_called()
        msg.nack.assert_called_once()
