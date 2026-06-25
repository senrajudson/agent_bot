"""Characterization tests for route_message (TASK-007).

Locks down the router behavior:
- Valid JSON response → correct route
- Invalid JSON → fallback to conversa_comum
- LLM exception → fallback to conversa_comum
- Empty message → fallback to conversa_comum
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestRouteMessageLLMCorrect:
    """R-1: LLM returns valid JSON with a known route."""

    @pytest.mark.asyncio
    async def test_route_returns_pims_for_valid_json(self, monkeypatch):
        from app.agent.router import route_message

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"rota": "pims"}'

        async def mock_acompletion(**kwargs):
            return mock_response

        monkeypatch.setattr("app.agent.router.litellm.acompletion", mock_acompletion)

        result = await route_message("qual o valor da tag X")
        assert result.rota == "pims"

    @pytest.mark.asyncio
    async def test_route_returns_general_for_valid_json(self, monkeypatch):
        from app.agent.router import route_message

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"rota": "conversa_comum"}'

        async def mock_acompletion(**kwargs):
            return mock_response

        monkeypatch.setattr("app.agent.router.litellm.acompletion", mock_acompletion)

        result = await route_message("ola")
        assert result.rota == "conversa_comum"


class TestRouteMessageLLMInvalid:
    """R-2: LLM returns invalid JSON → fallback."""

    @pytest.mark.asyncio
    async def test_route_fallback_on_invalid_json(self, monkeypatch):
        from app.agent.router import route_message

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "this is not json"

        async def mock_acompletion(**kwargs):
            return mock_response

        monkeypatch.setattr("app.agent.router.litellm.acompletion", mock_acompletion)

        result = await route_message("mensagem qualquer")
        assert result.rota == "conversa_comum"


class TestRouteMessageLLMException:
    """R-3: LLM raises exception → fallback."""

    @pytest.mark.asyncio
    async def test_route_fallback_on_exception(self, monkeypatch):
        from app.agent.router import route_message

        async def mock_acompletion(**kwargs):
            raise RuntimeError("LLM down")

        monkeypatch.setattr("app.agent.router.litellm.acompletion", mock_acompletion)

        result = await route_message("mensagem qualquer")
        assert result.rota == "conversa_comum"


class TestRouteMessageEmpty:
    """R-4: Empty message → fallback."""

    @pytest.mark.asyncio
    async def test_route_fallback_on_empty_message(self):
        from app.agent.router import route_message

        result = await route_message("")
        assert result.rota == "conversa_comum"

    @pytest.mark.asyncio
    async def test_route_fallback_on_none_like_message(self):
        from app.agent.router import route_message

        result = await route_message("   ")
        assert result.rota == "conversa_comum"
