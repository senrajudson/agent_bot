"""
OCR — uses litellm.acompletion with multimodal content to extract text from images.
Replaces the previous LangChain Runnable chain.
"""

from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.prompts.ocr_query_prompt import SYSTEM_PROMPT, USER_PROMPT
from app.schemas.chat import ChatImage, OcrResult
from app.schemas.llm import LLMParams
from app.utils.ocr_treatment import tratar_saida_ocr
from app.agent.shared import (
    build_completion_kwargs,
    call_with_model_fallback,
    RETRYABLE_ERRORS,
)


OCR_LLM_PARAMS = LLMParams(
    temperature=0,
    num_ctx=8192,
    num_predict=512,
    top_p=0.1,
)


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


async def _call_llm_for_ocr(messages: list[dict[str, Any]]) -> Any:
    """Route to model-fallback helper for Gemini, or standard retry for others."""
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "gemini":
        return await call_with_model_fallback(OCR_LLM_PARAMS, messages)
    kwargs = build_completion_kwargs(OCR_LLM_PARAMS)
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(RETRYABLE_ERRORS),
        reraise=True,
    ):
        with attempt:
            return await litellm.acompletion(**kwargs, messages=messages)


async def run_ocr_for_image(
    image: ChatImage,
    fallback_index: int = 0,
) -> OcrResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_content(image)},
    ]

    response = await _call_llm_for_ocr(messages)
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
