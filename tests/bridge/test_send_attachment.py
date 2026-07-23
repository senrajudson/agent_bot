from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.bridge.google_chat.chat_client import GoogleChatClient
from app.bridge.google_chat.config import GoogleChatBridgeSettings


def _make_settings() -> GoogleChatBridgeSettings:
    return GoogleChatBridgeSettings(
        GOOGLE_CLOUD_PROJECT="test-project",
        GOOGLE_CHAT_SUBSCRIPTION="projects/test-project/subscriptions/test",
        GOOGLE_APPLICATION_CREDENTIALS="/tmp/test-non-existent",
        AGENT_INTERNAL_URL="http://localhost:8002/chat",
        GOOGLE_CHAT_SCOPES="https://www.googleapis.com/auth/chat.bot",
        REDIS_URL="redis://localhost:6379/0",
        ENABLE_CHAT_ATTACHMENTS=True,
        AGENT_ARTIFACT_BASE_URL="http://localhost:8002/artifacts",
        AGENT_ARTIFACT_TOKEN="test-token",
        GOOGLE_CHAT_MAX_ATTACHMENTS_PER_MESSAGE=3,
    )


def test_send_attachment_validates_path():
    with patch.object(GoogleChatBridgeSettings, "validate_google_chat_config", return_value=None):
        settings = _make_settings()
        client = GoogleChatClient(settings=settings)
    client._service = MagicMock()

    try:
        client.send_attachment(
            space_name="spaces/test",
            file_path="/nonexistent/file.txt",
            mime_type="text/plain",
            filename="test.txt",
        )
        assert False, "Expected ValueError for nonexistent file"
    except ValueError as exc:
        assert "Arquivo não encontrado" in str(exc)


@patch("googleapiclient.http.MediaFileUpload")
def test_send_attachment_media_upload(mock_media_upload):
    with patch.object(GoogleChatBridgeSettings, "validate_google_chat_config", return_value=None):
        settings = _make_settings()
        client = GoogleChatClient(settings=settings)
    mock_service = MagicMock()
    mock_create = mock_service.spaces().messages().create
    mock_create.return_value.execute.return_value = {"name": "spaces/test/messages/1"}
    client._service = mock_service

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("test content")
        tmp_path = f.name

    try:
        result = client.send_attachment(
            space_name="spaces/test",
            file_path=tmp_path,
            mime_type="text/plain",
            filename="test.txt",
        )
        assert result["name"] == "spaces/test/messages/1"
        mock_media_upload.assert_called_once_with(
            filename=tmp_path, mimetype="text/plain", resumable=True
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@patch("httpx.Client")
def test_bridge_artifact_client_404(mock_httpx_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_httpx_client.return_value.__enter__.return_value.get.return_value = mock_resp

    from app.bridge.google_chat.bridge_internal_artifact_client import (
        BridgeArtifactClient,
        BridgeArtifactNotFound,
    )

    client = BridgeArtifactClient(
        base_url="http://test/artifacts",
        token="test",
        timeout=5,
    )
    try:
        client.get_metadata("nonexistent-id")
        assert False, "Expected BridgeArtifactNotFound"
    except BridgeArtifactNotFound:
        pass
