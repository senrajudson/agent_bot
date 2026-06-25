"""Characterization tests for parse_google_chat_event (TASK-008).

Locks down the parser behavior:
- Complete payload → can_process=True
- SPACE_EVENT → can_process=False
- BOT sender → can_process=False
- Minimal payload → defaults
"""
from __future__ import annotations

import pytest

from app.bridge.google_chat.parser import parse_google_chat_event


def _make_payload(
    event_type="MESSAGE",
    user_type="HUMAN",
    text="hello",
    space_name="spaces/abc",
    message_name="spaces/abc/messages/123",
    attachments=None,
):
    """Build a Google Chat Pub/Sub payload matching the real structure.

    The parser expects messagePayload inside chat, not as a sibling.
    """
    message = {
        "name": message_name,
        "text": text,
        "argumentText": text,
        "sender": {"name": "users/u1", "type": user_type},
        "space": {"name": space_name, "type": "SPACE"},
    }
    if attachments:
        message["attachment"] = attachments

    return {
        "payload": {
            "chat": {
                "user": {"type": user_type, "name": "users/u1"},
                "eventTime": "2026-01-01T00:00:00Z",
                "messagePayload": {
                    "message": message,
                    "eventType": event_type,
                },
            },
            "commonEventObject": {
                "timeZone": {"id": "America/Sao_Paulo", "offset": -10800},
            },
        },
        "pubsubMessageId": "ps-1",
    }


class TestParserCompletePayload:
    """P-1: Complete payload with message + sender + space."""

    def test_complete_message_payload(self):
        payload = _make_payload()
        event = parse_google_chat_event(payload)

        assert event.event_type == "MESSAGE"
        assert event.space_name == "spaces/abc"
        assert event.message_name == "spaces/abc/messages/123"
        assert event.message_text == "hello"
        assert event.user.type == "HUMAN"
        assert event.can_process is True

    def test_message_with_attachments(self):
        attachments = [
            {
                "name": "attachments/a1",
                "contentName": "image.png",
                "contentType": "image/png",
                "source": "UPLOADED_CONTENT",
                "attachmentDataRef": {"resourceName": "resource/123"},
            }
        ]
        payload = _make_payload(attachments=attachments)
        event = parse_google_chat_event(payload)

        assert event.has_attachments is True
        assert len(event.attachments) == 1
        assert event.attachments[0].content_type == "image/png"
        assert event.can_process is True


class TestParserSpaceEvent:
    """P-2: SPACE_EVENT → can_process=False."""

    def test_space_event_not_processable(self):
        payload = _make_payload(event_type="SPACE_EVENT")
        event = parse_google_chat_event(payload)

        assert event.event_type == "SPACE_EVENT"
        assert event.can_process is False


class TestParserBotSender:
    """P-3: BOT sender → can_process=False."""

    def test_bot_message_not_processable(self):
        payload = _make_payload(user_type="BOT")
        event = parse_google_chat_event(payload)

        assert event.user.type == "BOT"
        assert event.is_from_bot is True
        assert event.can_process is False


class TestParserMinimalPayload:
    """P-4: Minimal payload → defaults."""

    def test_empty_payload(self):
        event = parse_google_chat_event({})

        assert event.event_type == "UNKNOWN"
        assert event.space_name == ""
        assert event.message_name == ""
        assert event.can_process is False

    def test_none_payload_raises(self):
        """parse_google_chat_event(None) raises AttributeError (current behavior)."""
        with pytest.raises(AttributeError):
            parse_google_chat_event(None)
