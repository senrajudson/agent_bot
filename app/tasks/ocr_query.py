from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

from app.clients.provider_client import get_llm
from app.schemas.chat import ChatImage, OcrResult
from app.schemas.llm import LLMParams, AGENT_DEFAULT
from app.utils.ocr_treatment import tratar_saida_ocr
from app.prompts.ocr_query_prompt import SYSTEM_PROMPT, USER_PROMPT


OCR_LLM_PARAMS = LLMParams(
    **AGENT_DEFAULT,
    max_tokens=512,
    # num_predict=512,
    # think=False,
)


def _build_ocr_messages(payload: dict) -> list:
    image: ChatImage = payload["image"]

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": USER_PROMPT,
                },
                {
                    "type": "image",
                    "base64": image.image_base64,
                    "mime_type": image.mime_type or "image/png",
                },
            ]
        ),
    ]


def _treat_ocr_text(text: str):
    return tratar_saida_ocr(text)


ocr_chain = (
    RunnableLambda(_build_ocr_messages)
    | get_llm(OCR_LLM_PARAMS)
    | StrOutputParser()
    | RunnableLambda(_treat_ocr_text)
)


async def run_ocr_for_image(
    image: ChatImage,
    fallback_index: int = 0,
) -> OcrResult:
    treatment = await ocr_chain.ainvoke(
        {
            "image": image,
        }
    )

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
        result = await run_ocr_for_image(
            image=image,
            fallback_index=index,
        )
        results.append(result)

    return results