"""
OCR — uses litellm.acompletion with multimodal content to extract text from images.
Replaces the previous LangChain Runnable chain.
"""

from typing import Any

import litellm

from app.core.config import settings
from app.prompts.ocr_query_prompt import SYSTEM_PROMPT, USER_PROMPT
from app.schemas.chat import ChatImage, OcrResult
from app.schemas.llm import LLMParams
from app.utils.ocr_treatment import tratar_saida_ocr


OCR_LLM_PARAMS = LLMParams(
    temperature=0,
    num_predict=512,
    top_p=0.1,
)


def _build_completion_kwargs() -> dict[str, Any]:
    provider = settings.LLM_PROVIDER.lower().strip()
    kwargs: dict[str, Any] = {
        "temperature": OCR_LLM_PARAMS.temperature,
    }

    if OCR_LLM_PARAMS.num_predict is not None:
        kwargs["max_tokens"] = OCR_LLM_PARAMS.num_predict

    if OCR_LLM_PARAMS.top_p is not None:
        kwargs["top_p"] = OCR_LLM_PARAMS.top_p

    if provider == "gemini":
        kwargs["model"] = f"gemini/{settings.GEMINI_MODEL}"
        kwargs["api_key"] = settings.GEMINI_API_KEY
    elif provider == "groq":
        kwargs["model"] = f"groq/{settings.GROQ_MODEL}"
        kwargs["api_key"] = settings.GROQ_API_KEY
    elif provider == "ollama":
        kwargs["model"] = f"ollama_chat/{settings.OLLAMA_MODEL}"
        kwargs["api_base"] = settings.OLLAMA_BASE_URL
        if OCR_LLM_PARAMS.keep_alive is not None:
            kwargs["keep_alive"] = str(OCR_LLM_PARAMS.keep_alive)
    elif provider in {"openai_compatible", "openai-compatible", "openai"}:
        kwargs["model"] = f"openai/{settings.OPENAI_COMPATIBLE_MODEL}"
        kwargs["api_key"] = settings.OPENAI_COMPATIBLE_API_KEY
        kwargs["api_base"] = settings.OPENAI_COMPATIBLE_BASE_URL
    else:
        raise ValueError(f"LLM_PROVIDER inválido: {settings.LLM_PROVIDER}")

    return kwargs


def _build_user_content(image: ChatImage) -> list[dict[str, Any]]:
    mime = image.mime_type or "image/png"
    return [
        {"type": "text", "text": USER_PROMPT},
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{image.image_base64}",
            },
        },
    ]


async def run_ocr_for_image(
    image: ChatImage,
    fallback_index: int = 0,
) -> OcrResult:
    kwargs = _build_completion_kwargs()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_content(image)},
    ]

    response = await litellm.acompletion(**kwargs, messages=messages)
    raw_text = (response.choices[0].message.content or "").strip()

    treatment = tratar_saida_ocr(raw_text)

    image_index = image.image_index
    if image_index is None:
        image_index = fallback_index

    return OcrResult(
        image_index=image_index,
        file_name=image.file_name,
        mime_type=image.mime_type,
        texto_ocr_original=treatment.texto_ocr_original,
        texto_ocr_normalizado=treatment.texto_ocr_normalizado,
        tags_encontradas=treatment.tags_encontradas,
        resultado=treatment.resultado,
    )


async def run_ocr_for_images(images: list[ChatImage]) -> list[OcrResult]:
    results: list[OcrResult] = []
    for index, image in enumerate(images):
        result = await run_ocr_for_image(image=image, fallback_index=index)
        results.append(result)
    return results
