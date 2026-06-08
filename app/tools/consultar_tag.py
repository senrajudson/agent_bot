from langchain_core.tools import tool
from pydantic import BaseModel, Field, ConfigDict

from app.services.consultar_tag_service import consultar_tags_pi


class ConsultarTagInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str] = Field(
        description=(
            "Lista de tags do PI System que devem ser consultadas. "
            "Use esta lista para valor atual, descrição, unidade de engenharia, tipo, "
            "digital set, digital states, locations, instrumenttag e metadados de tags. "
            "Preserve exatamente os nomes das tags informadas pelo usuário. "
            "Nunca altere, traduza, abrevie ou escape underscores das tags. "
            "Não envie lista vazia."
        ),
    )

    pergunta_usuario: str | None = Field(
        default=None,
        description=(
            "Pergunta original do usuário. "
            "Preencha sempre que possível para preservar a intenção original, como valor atual, "
            "descrição, unidade, tipo da tag, digital set, estados digitais, locations ou metadados. "
            "Este campo é apenas contexto; as tags devem estar explicitamente no campo tags."
        ),
    )


async def consultar_tag(state: dict) -> dict:
    message = (
        state.get("processed_message")
        or state.get("rewritten_message")
        or state.get("message_original")
        or ""
    )

    tags_consultadas = (
        state.get("tags")
        or state.get("tags_consultadas")
        or state.get("tags_encontradas")
        or []
    )

    if not tags_consultadas:
        state["tool_name"] = "consultar_tag"
        state["tags_consultadas"] = []
        state["tool_result"] = None
        state["output"] = (
            "Não identifiquei nenhuma tag para consultar. "
            "Informe o nome da tag do PI System."
        )
        state["answer_generation_error"] = None
        return state

    result = await consultar_tags_pi(
        tags=tags_consultadas,
        pergunta_usuario=message,
        include_raw_response=True,
    )

    state["tool_name"] = "consultar_tag"
    state["tags_consultadas"] = result["tags_consultadas"]
    state["tool_result"] = result["tool_result"]
    state["output"] = result["output"]
    state["answer_generation_error"] = result["answer_generation_error"]

    return state


@tool(args_schema=ConsultarTagInput)
async def consultar_tag_tool(
    tags: list[str],
    pergunta_usuario: str | None = None,
) -> str:
    """
    Consulta valor atual, descrição, unidade de engenharia, tipo, digital set,
    locations, estados digitais e metadados de tags do PI System.

    Use esta tool quando o usuário pedir:
    - valor atual de uma tag;
    - descrição de uma tag;
    - unidade de engenharia;
    - tipo da tag;
    - digital set;
    - estados digitais;
    - locations;
    - instrumenttag;
    - metadados de tags do PI System;
    - informações cadastrais de uma ou mais tags.

    Contrato:
    - Sempre envie todos os campos do schema.
    - tags deve conter explicitamente as tags a consultar.
    - pergunta_usuario deve conter a pergunta original do usuário, quando disponível.
    - Não envie campos fora do schema.
    - A tool não extrai tags automaticamente do texto.
    - A tool não mescla tags automaticamente.
    - O agente deve identificar e preencher as tags antes de chamar esta tool.
    - Preserve exatamente os nomes das tags.
    - Nunca escape underscores.

    Exemplo - valor atual:
    Usuário: "Qual é o valor atual da tag CDT158 e SINUSOID?"
    Use:
    consultar_tag_tool({
        "tags": ["CDT158", "SINUSOID"],
        "pergunta_usuario": "Qual é o valor atual da tag CDT158 e SINUSOID?"
    })

    Exemplo - descrição e unidade:
    Usuário: "Me mostre a descrição e unidade da tag ACI_LC2_TEMP_FORNO."
    Use:
    consultar_tag_tool({
        "tags": ["ACI_LC2_TEMP_FORNO"],
        "pergunta_usuario": "Me mostre a descrição e unidade da tag ACI_LC2_TEMP_FORNO."
    })

    Exemplo - digital set:
    Usuário: "Qual é o digital set da tag CPD_LP_SECADOR_STATUS?"
    Use:
    consultar_tag_tool({
        "tags": ["CPD_LP_SECADOR_STATUS"],
        "pergunta_usuario": "Qual é o digital set da tag CPD_LP_SECADOR_STATUS?"
    })

    Exemplo - múltiplas tags:
    Usuário: "Consulte as tags CPD_LP_SECADOR_STATUS e CDT158."
    Use:
    consultar_tag_tool({
        "tags": ["CPD_LP_SECADOR_STATUS", "CDT158"],
        "pergunta_usuario": "Consulte as tags CPD_LP_SECADOR_STATUS e CDT158."
    })

    Regras reforçadas pelos exemplos:
    - Use consultar_tag_tool somente para valor atual e metadados de tags.
    - O agente deve preencher tags explicitamente.
    - A tool não tenta descobrir tags sozinha.
    - Se a pergunta envolver período histórico, use tag_statistics_tool ou tag_calculus_tool.
    - Se a pergunta envolver status do PIMS, use status_pims_tool.
    """

    result = await consultar_tags_pi(
        tags=tags,
        pergunta_usuario=pergunta_usuario or "",
        include_raw_response=False,
    )

    return result["output"]