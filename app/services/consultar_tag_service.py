from typing import Any

from app.clients.pi_web_api_client import get_tags_data
from app.utils.digital_states import enriquecer_com_digital_states
from app.utils.pi_response_formatter import (
    format_pi_batch_response,
    formatar_mensagem_tags,
)
from app.utils.tag_extractor import merge_unique_tags


async def consultar_tags_pi(
    tags: list[str],
    pergunta_usuario: str = "",
    include_raw_response: bool = True,
) -> dict[str, Any]:
    tags_consultadas = merge_unique_tags(tags)

    if not tags_consultadas:
        return {
            "ok": False,
            "tags_consultadas": [],
            "tool_result": {
                "tags_consultadas": [],
                "resultados_pi": [],
                "tem_tag_digital": False,
            },
            "output": (
                "Não encontrei nenhuma tag válida na mensagem. "
                "Verifique o nome da tag e tente novamente."
            ),
            "answer_generation_error": None,
        }

    raw_pi_response = await get_tags_data(tags_consultadas)

    formatted_response = format_pi_batch_response(raw_pi_response)

    digital_info = await enriquecer_com_digital_states(
        formatted_response["resultados_pi"]
    )

    resultados_pi = digital_info["resultados_pi"]

    dados_atualizados = formatar_mensagem_tags(resultados_pi)

    tool_result = {
        "tags_consultadas": tags_consultadas,
        "resultados_pi": resultados_pi,
        "mensagem_final_deterministica": dados_atualizados,
        "tem_tag_digital": digital_info["tem_tag_digital"],
        "qtd_tags_digitais": digital_info["qtd_tags_digitais"],
        "qtd_digital_sets": digital_info["qtd_digital_sets"],
        "digital_sets_consultados": digital_info["digital_sets_consultados"],
        "digital_states_por_set": digital_info["digital_states_por_set"],
    }

    if include_raw_response:
        tool_result["raw_pi_response"] = raw_pi_response

    return {
        "ok": True,
        "tags_consultadas": tags_consultadas,
        "tool_result": tool_result,
        "output": dados_atualizados,
        "answer_generation_error": None,
    }