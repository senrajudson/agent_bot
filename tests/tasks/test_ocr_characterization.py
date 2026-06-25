"""Characterization tests for run_ocr_for_images and tratar_saida_ocr (TASK-007).

Locks down OCR behavior:
- 1 image with tags → OcrResult with tags
- 0 images → empty list
- 2-3 images sequential → results in order
- tratar_saida_ocr with tags → extracted tags
- tratar_saida_ocr empty/None → empty result
- tratar_saida_ocr no tags → tags_encontradas=[]
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestRunOcrForImages:
    """O-1 to O-3: run_ocr_for_images behavior."""

    @pytest.mark.asyncio
    async def test_ocr_1_image_with_tags(self, monkeypatch):
        from app.schemas.chat import ChatImage

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"texto_ocr": "Tag: LFI_RB3_VAZ_GN_TOTAL valor: 1523", '
            '"tags": ["LFI_RB3_VAZ_GN_TOTAL"]}'
        )

        async def mock_acompletion(**kwargs):
            return mock_response

        monkeypatch.setattr("app.tasks.ocr_query.litellm.acompletion", mock_acompletion)

        from app.tasks.ocr_query import run_ocr_for_images

        images = [
            ChatImage(
                image_base64="iVBORw0KGgoAAAANSUhEUg==",
                mime_type="image/png",
                file_name="test.png",
                image_index=0,
            )
        ]
        results = await run_ocr_for_images(images)

        assert len(results) == 1
        assert results[0].tags_encontradas == ["LFI_RB3_VAZ_GN_TOTAL"]
        assert results[0].image_index == 0

    @pytest.mark.asyncio
    async def test_ocr_0_images(self):
        from app.tasks.ocr_query import run_ocr_for_images

        results = await run_ocr_for_images([])
        assert results == []

    @pytest.mark.asyncio
    async def test_ocr_multiple_images_sequential(self, monkeypatch):
        from app.schemas.chat import ChatImage

        call_count = {"n": 0}

        async def mock_acompletion(**kwargs):
            call_count["n"] += 1
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = (
                f'{{"texto_ocr": "image {call_count["n"]}", "tags": []}}'
            )
            return mock_response

        monkeypatch.setattr("app.tasks.ocr_query.litellm.acompletion", mock_acompletion)

        from app.tasks.ocr_query import run_ocr_for_images

        images = [
            ChatImage(image_base64="AAA", mime_type="image/png", image_index=0),
            ChatImage(image_base64="BBB", mime_type="image/jpeg", image_index=1),
            ChatImage(image_base64="CCC", mime_type="image/png", image_index=2),
        ]
        results = await run_ocr_for_images(images)

        assert len(results) == 3
        assert results[0].image_index == 0
        assert results[1].image_index == 1
        assert results[2].image_index == 2
        assert call_count["n"] == 3


class TestTratarSaidaOcr:
    """O-4 to O-6: tratar_saida_ocr behavior."""

    def test_treatment_with_tags(self):
        from app.utils.ocr_treatment import tratar_saida_ocr

        text = 'Tag: LFI_RB3_VAZ_GN_TOTAL valor: 1523. Outra tag: ACI_001_TEMP'
        result = tratar_saida_ocr(text)

        assert "LFI_RB3_VAZ_GN_TOTAL" in result.tags_encontradas
        assert "ACI_001_TEMP" in result.tags_encontradas

    def test_treatment_empty_string(self):
        from app.utils.ocr_treatment import tratar_saida_ocr

        result = tratar_saida_ocr("")

        assert result.tags_encontradas == []
        assert result.texto_ocr_normalizado == "[Nenhum texto encontrado]"

    def test_treatment_no_tags(self):
        from app.utils.ocr_treatment import tratar_saida_ocr

        result = tratar_saida_ocr("texto sem nenhuma tag aqui")

        assert result.tags_encontradas == []
