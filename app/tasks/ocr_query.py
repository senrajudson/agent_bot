"""
OCR — uses litellm.acompletion with multimodal content to extract text from images.
Replaces the previous LangChain Runnable chain.
"""

from typing import Any

import litellm

from app.prompts.ocr_query_prompt import SYSTEM_PROMPT, USER_PROMPT
from app.schemas.chat import ChatImage, OcrResult
from app.schemas.llm import LLMParams
from app.utils.ocr_treatment import tratar_saida_ocr
from app.agent.shared import build_completion_kwargs


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


async def run_ocr_for_image(
    image: ChatImage,
    fallback_index: int = 0,
) -> OcrResult:
    kwargs = build_completion_kwargs(OCR_LLM_PARAMS)

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
