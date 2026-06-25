"""Characterization tests for AgentAdapter.ask (TASK-008).

Locks down the AgentAdapter behavior:
- JSON response with 'output' key → extracts output
- JSON response with 'response' key → extracts response
- Plain text response → returns text
- HTTP 500 → raises RuntimeError
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.bridge.google_chat.agent_adapter import AgentAdapter
from app.bridge.google_chat.config import GoogleChatBridgeSettings
from app.bridge.google_chat.models import GoogleChatIncomingMessage


def _fake_event(**overrides) -> GoogleChatIncomingMessage:
    defaults = dict(
        message_name="spaces/abc/messages/1",
        space_name="spaces/abc",
        event_type="MESSAGE",
        message_text="hello",
        argument_text="hello",
    )
    defaults.update(overrides)
    return GoogleChatIncomingMessage(**defaults)


def _fake_settings() -> GoogleChatBridgeSettings:
    s = MagicMock(spec=GoogleChatBridgeSettings)
    s.agent_internal_url = "http://localhost:8002/chat"
    s.validate_google_chat_config = MagicMock()
    return s


class TestAgentAdapterExtractOutput:
    """A-1: JSON with 'output' key."""

    def test_extracts_output_key(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"output": "resposta do agente"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=mock_response)))
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            adapter = AgentAdapter(settings=_fake_settings())
            result = adapter.ask(event=_fake_event())

        assert result == "resposta do agente"


class TestAgentAdapterExtractResponse:
    """A-2: JSON with 'response' key."""

    def test_extracts_response_key(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"response": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=mock_response)))
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            adapter = AgentAdapter(settings=_fake_settings())
            result = adapter.ask(event=_fake_event())

        assert result == "ok"


class TestAgentAdapterPlainText:
    """A-3: Plain text response."""

    def test_extracts_plain_text(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "resposta em texto"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=mock_response)))
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            adapter = AgentAdapter(settings=_fake_settings())
            result = adapter.ask(event=_fake_event())

        assert result == "resposta em texto"


class TestAgentAdapterHTTPError:
    """A-4: HTTP 500 → RuntimeError."""

    def test_raises_on_500(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        http_error = MagicMock()
        http_error.response = mock_response

        import httpx
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                message="500", request=MagicMock(), response=mock_response,
            )
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            adapter = AgentAdapter(settings=_fake_settings())
            with pytest.raises(RuntimeError, match="HTTP"):
                adapter.ask(event=_fake_event())
