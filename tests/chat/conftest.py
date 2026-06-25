"""Shared fixtures for /chat characterization tests (TASK-006).

Neutralizes Phoenix tracing before importing app.main.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatImage, ChatRequest


# ---------------------------------------------------------------------------
# Phoenix neutralization — applied BEFORE import of app.main
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_client():
    """Import app.main inside the patch context to prevent Phoenix init."""
    with patch(
        "app.observability.phoenix.setup_phoenix_tracing",
    ):
        from fastapi.testclient import TestClient

        from app.main import app as _app

        client = TestClient(_app)
        yield client


# ---------------------------------------------------------------------------
# ChatRequest builders
# ---------------------------------------------------------------------------

@pytest.fixture()
def chat_payload_text() -> ChatRequest:
    """Plain text message, no images."""
    return ChatRequest(
        message="qual o valor da LFI_RB3_VAZ_GN_TOTAL",
        user_id="test-user-001",
    )


@pytest.fixture()
def chat_payload_with_image() -> ChatRequest:
    """Message with one image."""
    return ChatRequest(
        message="analise essa imagem",
        user_id="test-user-002",
        images=[
            ChatImage(
                image_base64="iVBORw0KGgoAAAANSUhEUg==",
                mime_type="image/png",
                file_name="diagram.png",
                image_index=0,
            )
        ],
    )


@pytest.fixture()
def chat_payload_with_multiple_images() -> ChatRequest:
    """Message with 3 images (for sequencing test)."""
    return ChatRequest(
        message="analise essas imagens",
        user_id="test-user-003",
        images=[
            ChatImage(
                image_base64="iVBORw0KGgoAAAANSUhEUg==",
                mime_type="image/png",
                file_name="img1.png",
                image_index=0,
            ),
            ChatImage(
                image_base64="iVBORw0KGgoAAAANSUhEUg==",
                mime_type="image/jpeg",
                file_name="img2.jpg",
                image_index=1,
            ),
            ChatImage(
                image_base64="iVBORw0KGgoAAAANSUhEUg==",
                mime_type="image/png",
                file_name="img3.png",
                image_index=2,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Mock callables — monkeypatched at the usage site
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_route_general(monkeypatch):
    """Router returns 'conversa_comum'."""
    from app.agent.router import RouterOutput

    async def _route(**kwargs):
        return RouterOutput(rota="conversa_comum")

    monkeypatch.setattr("app.agent.orchestrator.route_message", _route)
    return _route


@pytest.fixture()
def mock_route_pims(monkeypatch):
    """Router returns 'pims'."""
    from app.agent.router import RouterOutput

    async def _route(**kwargs):
        return RouterOutput(rota="pims")

    monkeypatch.setattr("app.agent.orchestrator.route_message", _route)
    return _route


@pytest.fixture()
def mock_general_agent(monkeypatch):
    """General agent returns fixed output."""
    async def _agent(**kwargs):
        return {"output": "Olá! Como posso ajudar?", "messages": [], "error": None}

    monkeypatch.setattr("app.agent.orchestrator.run_general_agent", _agent)
    return _agent


@pytest.fixture()
def mock_general_agent_error(monkeypatch):
    """General agent raises an exception."""
    async def _agent(**kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr("app.agent.orchestrator.run_general_agent", _agent)
    return _agent


@pytest.fixture()
def mock_pi_agent(monkeypatch):
    """PI agent returns fixed output."""
    async def _agent(**kwargs):
        return {
            "output": "O valor atual de LFI_RB3_VAZ_GN_TOTAL é 1523.4 Nm3/h",
            "error": None,
            "messages": [],
        }

    monkeypatch.setattr("app.agent.orchestrator.run_pi_agent", _agent)
    return _agent


@pytest.fixture()
def mock_ocr_no_images(monkeypatch):
    """OCR returns empty list (no images)."""
    async def _ocr(images):
        return []

    monkeypatch.setattr("app.agent.orchestrator.run_ocr_for_images", _ocr)
    return _ocr


@pytest.fixture()
def mock_ocr_with_tags(monkeypatch):
    """OCR returns results with extracted tags."""
    from app.schemas.chat import OcrResult

    async def _ocr(images):
        return [
            OcrResult(
                image_index=i,
                file_name=f"img{i}.png",
                mime_type="image/png",
                texto_ocr_original=f"Tag: LFI_RB3_VAZ_GN_TOTAL valor: 15{i}",
                texto_ocr_normalizado=f"Tag: LFI_RB3_VAZ_GN_TOTAL valor: 15{i}",
                tags_encontradas=["LFI_RB3_VAZ_GN_TOTAL"],
                resultado=f"Tag: LFI_RB3_VAZ_GN_TOTAL valor: 15{i}",
            )
            for i in range(len(images))
        ]

    monkeypatch.setattr("app.agent.orchestrator.run_ocr_for_images", _ocr)
    return _ocr


@pytest.fixture()
def mock_ocr_no_tags(monkeypatch):
    """OCR returns results without tags."""
    from app.schemas.chat import OcrResult

    async def _ocr(images):
        return [
            OcrResult(
                image_index=i,
                file_name=f"img{i}.png",
                mime_type="image/png",
                texto_ocr_original="sem tags",
                texto_ocr_normalizado="sem tags",
                tags_encontradas=[],
                resultado="sem tags",
            )
            for i in range(len(images))
        ]

    monkeypatch.setattr("app.agent.orchestrator.run_ocr_for_images", _ocr)
    return _ocr


@pytest.fixture()
def mock_redis(monkeypatch):
    """Mock Redis client for memory load/save.

    lrange must be awaitable because chat_memory_service does:
        raw_items = await redis.lrange(key, -limit, -1)
    """
    mock_client = MagicMock()
    mock_client.lrange = AsyncMock(return_value=[])
    mock_pipe = MagicMock()
    mock_pipe.rpush = MagicMock()
    mock_pipe.ltrim = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_pipe.execute = MagicMock(return_value=[None, None, None])
    mock_client.pipeline.return_value = mock_pipe

    monkeypatch.setattr(
        "app.services.chat_memory_service.get_redis_client",
        lambda: mock_client,
    )
    return mock_client
