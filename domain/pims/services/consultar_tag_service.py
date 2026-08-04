from typing import Any

from domain.pims.clients.pi_web_api_client import get_tags_data
from domain.pims.utils.digital_states import enriquecer_com_digital_states
from domain.pims.utils.pi_response_formatter import (
    extract_unresolved_subresponse_indices,
    format_pi_batch_response,
    formatar_mensagem_tags,
)
from domain.pims.utils.tag_extractor import merge_unique_tags


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

    unresolved_indices = extract_unresolved_subresponse_indices(
        raw_pi_response, expected_count=len(tags_consultadas)
    )
    unresolved_tags = [tags_consultadas[i] for i in unresolved_indices]

    formatted_response = format_pi_batch_response(raw_pi_response)

    resultados_pi_all = formatted_response["resultados_pi"]
    if unresolved_indices:
        unresolved_set = set(unresolved_indices)
        resultados_pi_filtered = [
            r for i, r in enumerate(resultados_pi_all)
            if i not in unresolved_set
        ]
    else:
        resultados_pi_filtered = resultados_pi_all

    digital_info = await enriquecer_com_digital_states(resultados_pi_filtered)

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

    if unresolved_tags:
        tool_result["tags_nao_resolvidas"] = unresolved_tags

    if include_raw_response:
        tool_result["raw_pi_response"] = raw_pi_response

    return {
        "ok": True,
        "tags_consultadas": tags_consultadas,
        "tool_result": tool_result,
        "output": dados_atualizados,
        "answer_generation_error": None,
    }