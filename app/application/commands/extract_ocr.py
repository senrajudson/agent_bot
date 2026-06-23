"""Command: Extract text and tags from images via OCR."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.application.commands.base import Command
from app.domain.protocols import OcrExtractionLike, OcrService


@dataclass(frozen=True)
class ExtractOcr(Command):
    """Request OCR extraction for a list of images."""

    images: list  # list[ChatImage] — kept as Any to avoid infra import


@dataclass(frozen=True)
class ExtractOcrResult:
    """Result of OCR extraction."""

    extractions: list[OcrExtractionLike] = field(default_factory=list)


class ExtractOcrHandler:
    """Extracts text and industrial tags from images using a multimodal LLM.

    Delegates to an OcrService (injected via constructor).
    No direct dependency on litellm, httpx, or any infrastructure.
    """

    def __init__(self, ocr_service: OcrService) -> None:
        self._ocr = ocr_service

    async def handle(self, command: ExtractOcr) -> ExtractOcrResult:
        if not command.images:
            return ExtractOcrResult(extractions=[])

        extractions = await self._ocr.extract_batch(command.images)
        return ExtractOcrResult(extractions=extractions)
