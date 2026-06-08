from typing import Any

from pydantic import BaseModel, Field


class ChatImage(BaseModel):
    image_base64: str = Field(..., min_length=1)
    mime_type: str = "image/png"
    file_name: str | None = None
    image_index: int | None = None


class ChatRequest(BaseModel):
    message: str = ""
    user_id: str | None = None
    images: list[ChatImage] = Field(default_factory=list)


class OcrResult(BaseModel):
    image_index: int
    file_name: str | None = None
    mime_type: str

    texto_ocr_original: str
    texto_ocr_normalizado: str
    tags_encontradas: list[str] = Field(default_factory=list)
    resultado: str


class ChatResponse(BaseModel):
    ok: bool
    user_id: str | None = None

    message_original: str
    processed_message: str | None = None

    categoria: str | None = None
    next_action: str | None = None

    has_image: bool
    skip_ocr: bool

    ocr_text: str | None = None
    tags_encontradas: list[str] = Field(default_factory=list)
    tags_consultadas: list[str] = Field(default_factory=list)
    ocr_results: list[OcrResult] = Field(default_factory=list)

    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)

    output: str | None = None
    answer_generation_error: str | None = None