"""Characterization tests for GoogleChatMediaDownloader (TASK-008).

Locks down the media downloader behavior:
- content_type not image → ignored
- source != UPLOADED_CONTENT → ignored
- resource_name empty → ignored
- max_images exceeded → truncated to limit
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.bridge.google_chat.media_downloader import GoogleChatMediaDownloader
from app.bridge.google_chat.models import GoogleChatAttachment, GoogleChatIncomingMessage


def _make_attachment(
    content_type="image/png",
    source="UPLOADED_CONTENT",
    resource_name="resource/123",
    content_name="img.png",
) -> GoogleChatAttachment:
    return GoogleChatAttachment(
        name="attachments/a1",
        content_name=content_name,
        content_type=content_type,
        resource_name=resource_name,
        source=source,
    )


def _make_event(attachments: list[GoogleChatAttachment]) -> GoogleChatIncomingMessage:
    return GoogleChatIncomingMessage(
        message_name="spaces/abc/messages/1",
        space_name="spaces/abc",
        event_type="MESSAGE",
        message_text="check image",
        attachments=attachments,
    )


def _mock_downloader(max_images=4) -> GoogleChatMediaDownloader:
    settings = MagicMock()
    settings.validate_google_chat_config = MagicMock()
    return GoogleChatMediaDownloader(settings=settings, max_images=max_images)


class TestMediaDownloaderIgnored:
    """M-3 to M-5: attachments that should be ignored."""

    def test_content_type_not_image(self):
        downloader = _mock_downloader()
        event = _make_event([_make_attachment(content_type="application/pdf")])
        result = downloader.download_images_from_event(event)
        assert result == []

    def test_source_not_uploaded(self):
        downloader = _mock_downloader()
        event = _make_event([_make_attachment(source="DRIVE_FILE")])
        result = downloader.download_images_from_event(event)
        assert result == []

    def test_resource_name_empty(self):
        downloader = _mock_downloader()
        event = _make_event([_make_attachment(resource_name="")])
        result = downloader.download_images_from_event(event)
        assert result == []


class TestMediaDownloaderMaxImages:
    """M-6: max_images exceeded → truncated (only counts valid attachments)."""

    def test_max_images_truncated(self):
        downloader = _mock_downloader(max_images=2)
        # 5 valid attachments → only 2 downloaded
        attachments = [_make_attachment(content_name=f"img{i}.png") for i in range(5)]
        event = _make_event(attachments)

        # download_image_attachment will be called; mock it to avoid real API
        downloader.download_image_attachment = MagicMock(
            return_value=MagicMock(filename="img.png", content_type="image/png", size_bytes=100, base64_data="abc")
        )

        result = downloader.download_images_from_event(event)
        assert len(result) == 2
        assert downloader.download_image_attachment.call_count == 2

    def test_max_images_respected(self):
        downloader = _mock_downloader(max_images=1)
        attachments = [_make_attachment(content_name=f"img{i}.png") for i in range(3)]
        event = _make_event(attachments)

        downloader.download_image_attachment = MagicMock(
            return_value=MagicMock(filename="img.png", content_type="image/png", size_bytes=100, base64_data="abc")
        )

        result = downloader.download_images_from_event(event)
        assert len(result) == 1
