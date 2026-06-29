"""Characterization tests for POST /chat (TASK-006).

These tests lock down the HTTP-level contract of the /chat endpoint:
- Request/response shape
- Status code behavior
- Behavior with/without images
- Error propagation
- Envelope of 17 mandatory keys
"""
from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# Constant: 17 mandatory keys of ChatResponse
# ---------------------------------------------------------------------------
EXPECTED_17_KEYS = frozenset({
    "ok",
    "categoria",
    "next_action",
    "output",
    "tool_name",
    "tool_result",
    "agent_trace",
    "ocr_text",
    "ocr_results",
    "tags_encontradas",
    "tags_consultadas",
    "has_image",
    "skip_ocr",
    "message_original",
    "processed_message",
    "answer_generation_error",
    "user_id",
})


# ===========================================================================
# C-1: POST /chat sem imagem, rota conversa_comum
# ===========================================================================

class TestChatRouteGeneral:
    """C-1: /chat returns 200 with conversa_comum route."""

    def test_chat_text_only_returns_200_ok(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        data = response.json()

        assert data["ok"] is True
        assert data["categoria"] == "conversa_comum"
        assert data["next_action"] == "general_agent"
        assert data["has_image"] is False
        assert data["skip_ocr"] is True
        assert data["ocr_text"] is None
        assert data["tags_encontradas"] == []
        assert data["ocr_results"] == []

    def test_chat_text_only_preserves_user_id(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-001"

    def test_chat_text_only_preserves_message_original(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        data = response.json()
        assert data["message_original"] == "qual o valor da LFI_RB3_VAZ_GN_TOTAL"
        assert data["processed_message"] == data["message_original"]


# ===========================================================================
# C-2: POST /chat sem imagem, rota pims mockada
# ===========================================================================

class TestChatRoutePims:
    """C-2: /chat returns 200 with pims route."""

    def test_chat_pims_route_returns_200_ok(
        self,
        app_client,
        chat_payload_text,
        mock_route_pims,
        mock_agent,
        mock_ocr_no_images,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        data = response.json()

        assert data["ok"] is True
        assert data["categoria"] == "pims"
        assert data["next_action"] == "agent"
        assert "LFI_RB3_VAZ_GN_TOTAL" in (data["output"] or "")


# ===========================================================================
# C-3: POST /chat com 1 imagem, OCR mockado com tags
# ===========================================================================

class TestChatWithImageOcrTags:
    """C-3: /chat with image and OCR returning tags."""

    def test_chat_with_image_ocr_tags(
        self,
        app_client,
        chat_payload_with_image,
        mock_route_general,
        mock_general_agent,
        mock_ocr_with_tags,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_with_image.model_dump())

        assert response.status_code == 200
        data = response.json()

        assert data["has_image"] is True
        assert data["skip_ocr"] is False
        assert data["ocr_text"] is not None
        assert len(data["ocr_results"]) == 1
        assert "LFI_RB3_VAZ_GN_TOTAL" in data["tags_encontradas"]


# ===========================================================================
# C-4: POST /chat com imagem, OCR mockado sem tags
# ===========================================================================

class TestChatWithImageOcrNoTags:
    """C-4: /chat with image and OCR returning no tags."""

    def test_chat_with_image_ocr_no_tags(
        self,
        app_client,
        chat_payload_with_image,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_tags,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_with_image.model_dump())

        assert response.status_code == 200
        data = response.json()

        assert data["has_image"] is True
        assert data["skip_ocr"] is False
        assert data["ocr_text"] is not None
        assert data["tags_encontradas"] == []


# ===========================================================================
# C-5: POST /chat em erro controlado
# ===========================================================================

class TestChatErrorControlled:
    """C-5: /chat preserves status 200 when agent fails, ok=False in body."""

    def test_chat_agent_error_returns_200_ok_false(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent_error,
        mock_ocr_no_images,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        data = response.json()

        assert data["ok"] is False
        assert data["categoria"] == "erro_no_orchestrator"
        assert data["next_action"] == "orchestrator"
        assert data["answer_generation_error"] is not None
        assert "LLM unavailable" in data["answer_generation_error"]


# ===========================================================================
# C-6: ChatResponse envelope — 17 mandatory keys present
# ===========================================================================

class TestChatEnvelope:
    """C-6: /chat response contains all 17 mandatory keys."""

    def test_chat_response_has_all_17_keys(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        data = response.json()

        assert EXPECTED_17_KEYS.issubset(set(data.keys())), (
            f"Missing keys: {EXPECTED_17_KEYS - set(data.keys())}"
        )

    def test_chat_response_has_all_17_keys_on_error(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent_error,
        mock_ocr_no_images,
        mock_redis,
    ):
        response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        data = response.json()

        assert EXPECTED_17_KEYS.issubset(set(data.keys())), (
            f"Missing keys on error: {EXPECTED_17_KEYS - set(data.keys())}"
        )
