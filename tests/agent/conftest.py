"""Shared fixtures for agent characterization tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatRequest, ChatImage


# ---------------------------------------------------------------------------
# Fixtures: ChatRequest builders
# ---------------------------------------------------------------------------
@pytest.fixture
def simple_text_request():
    """A plain text message, no images, with user_id."""
    return ChatRequest(
        message="qual o valor da LFI_RB3_VAZ_GN_TOTAL",
        user_id="test-user-001",
    )


@pytest.fixture
def empty_message_request():
    """Empty message — edge case."""
    return ChatRequest(message="", user_id="test-user-002")


@pytest.fixture
def request_with_images():
    """Message with one image."""
    return ChatRequest(
        message="analise essa imagem",
        user_id="test-user-003",
        images=[
            ChatImage(
                image_base64="iVBORw0KGgoAAAANSUhEUg==",
                mime_type="image/png",
                file_name="diagram.png",
                image_index=0,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Fixtures: Mocked dependencies
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis lrange (memory load) and pipeline (memory save)."""
    mock_client = MagicMock()
    # lrange is async in the service
    mock_client.lrange = AsyncMock(return_value=[])

    # pipeline() returns a MagicMock with synchronous methods
    mock_pipe = MagicMock()
    mock_pipe.rpush = MagicMock()
    mock_pipe.ltrim = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[None, None, None])
    mock_client.pipeline.return_value = mock_pipe

    monkeypatch.setattr(
        "app.services.chat_memory_service.get_redis_client",
        lambda: mock_client,
    )
    return mock_client


@pytest.fixture
def mock_route_pims(monkeypatch):
    """Router returns 'pims' route."""
    from app.agent.router import RouterOutput

    async def _route_message(**kwargs):
        return RouterOutput(rota="pims")

    monkeypatch.setattr("app.agent.orchestrator.route_message", _route_message)
    return _route_message


@pytest.fixture
def mock_route_general(monkeypatch):
    """Router returns 'conversa_comum' route."""
    from app.agent.router import RouterOutput

    async def _route_message(**kwargs):
        return RouterOutput(rota="conversa_comum")

    monkeypatch.setattr("app.agent.orchestrator.route_message", _route_message)
    return _route_message


@pytest.fixture
def mock_route_error(monkeypatch):
    """Router raises an exception."""
    async def _route_message(**kwargs):
        raise RuntimeError("Router LLM unavailable")

    monkeypatch.setattr("app.agent.orchestrator.route_message", _route_message)
    return _route_message


@pytest.fixture
def mock_agent(monkeypatch):
    """Agent returns a fixed result."""
    async def _run_agent(**kwargs):
        return {
            "output": "O valor atual de LFI_RB3_VAZ_GN_TOTAL é 1523.4 Nm3/h",
            "error": None,
            "messages": [],
        }

    monkeypatch.setattr("app.agent.orchestrator.run_agent", _run_agent)
    return _run_agent


@pytest.fixture
def mock_general_agent(monkeypatch):
    """General agent returns a fixed result."""
    async def _run_general_agent(**kwargs):
        return {
            "output": "Olá! Como posso ajudar?",
            "messages": [],
        }

    monkeypatch.setattr("app.agent.orchestrator.run_general_agent", _run_general_agent)
    return _run_general_agent


@pytest.fixture
def mock_ocr_no_images(monkeypatch):
    """OCR returns empty list when no images."""
    async def _run_ocr_for_images(images):
        return []

    monkeypatch.setattr("app.agent.orchestrator.run_ocr_for_images", _run_ocr_for_images)
    return _run_ocr_for_images


@pytest.fixture
def mock_ocr_with_tags(monkeypatch):
    """OCR returns results with extracted tags."""
    from app.schemas.chat import OcrResult

    async def _run_ocr_for_images(images):
        return [
            OcrResult(
                image_index=0,
                file_name="diagram.png",
                mime_type="image/png",
                texto_ocr_original="Tag: LFI_RB3_VAZ_GN_TOTAL valor: 1523",
                texto_ocr_normalizado="Tag: LFI_RB3_VAZ_GN_TOTAL valor: 1523",
                tags_encontradas=["LFI_RB3_VAZ_GN_TOTAL"],
                resultado="Tag: LFI_RB3_VAZ_GN_TOTAL valor: 1523",
            )
        ]

    monkeypatch.setattr("app.agent.orchestrator.run_ocr_for_images", _run_ocr_for_images)
    return _run_ocr_for_images


@pytest.fixture
def mock_rag_empty(monkeypatch):
    """RAG returns empty context."""
    monkeypatch.setattr("app.agent.orchestrator.build_rag_context", lambda **kwargs: "")
    return None


@pytest.fixture
def mock_rag_with_context(monkeypatch):
    """RAG returns a fixed context string."""
    fake_context = (
        "---\nCONTEXTO DA DOCUMENTACAO PI WEB API:\n---\n\n"
        "# CHUNK 01 - Chunk fixo\nConteudo do chunk 01"
    )
    monkeypatch.setattr(
        "app.agent.orchestrator.build_rag_context",
        lambda **kwargs: fake_context,
    )
    return fake_context
