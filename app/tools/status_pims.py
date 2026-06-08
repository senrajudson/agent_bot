from pydantic import BaseModel, Field, ConfigDict
from langchain_core.tools import tool

from app.services.status_pims_service import consultar_status_pims_service


class StatusPimsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pergunta_usuario: str | None = Field(
        default=None,
        description=(
            "Texto original da pergunta do usuário. "
            "Preencha sempre que possível. "
            "Use esta informação para preservar o contexto operacional da solicitação, "
            "como PIMS fora, PI Web API com erro, servidor indisponível, lentidão, queda, "
            "falha em serviço, problema de logs, status atual ou saúde do ambiente."
        ),
    )

    lookback_minutes: int | None = Field(
        default=None,
        description=(
            "Quantidade de minutos para consultar nos logs do Grafana/Loki. "
            "Use somente quando o usuário informar um período claro ou quando a intenção pedir status atual. "
            "Exemplos: status atual = 60, últimas 2 horas = 120, últimos 30 minutos = 30, hoje = 1440, "
            "ontem ou desde ontem = 2880. "
            "Se não houver período claro e a pergunta não pedir status atual, envie null. "
            "Não invente períodos muito longos sem necessidade."
        ),
    )


async def consultar_status_pims(state: dict) -> dict:
    user_message = (
        state.get("processed_message")
        or state.get("rewritten_message")
        or state.get("message_original")
        or ""
    )

    result = await consultar_status_pims_service(
        user_message=user_message,
        lookback_minutes=state.get("lookback_minutes"),
        include_raw_response=True,
    )

    state["tool_name"] = result["tool_name"]
    state["tool_result"] = result["tool_result"]
    state["output"] = result["output"]
    state["answer_generation_error"] = result["answer_generation_error"]

    return state


@tool(args_schema=StatusPimsInput)
async def status_pims_tool(
    pergunta_usuario: str | None = None,
    lookback_minutes: int | None = None,
) -> str:
    """
    Consulta logs do Grafana/Loki para avaliar status, saúde, erro, lentidão,
    queda, indisponibilidade ou instabilidade do PIMS, PI Web API, servidores
    e serviços monitorados.

    Use esta tool quando o usuário perguntar:
    - se o PIMS está normal;
    - se o PIMS caiu;
    - se há lentidão no PIMS;
    - se a PI Web API está com erro;
    - se os servidores ou serviços monitorados estão com problema;
    - se houve indisponibilidade, falha, timeout, erro 500, erro 503 ou instabilidade;
    - qual é o status atual do ambiente.

    Contrato padronizado:
    - Sempre envie todos os campos do schema.
    - Preencha pergunta_usuario com a pergunta original do usuário.
    - Use lookback_minutes quando houver período claro.
    - Para status atual, saúde atual ou "PIMS está normal agora?", use lookback_minutes=60.
    - Para últimas 2 horas, use lookback_minutes=120.
    - Para últimos 30 minutos, use lookback_minutes=30.
    - Para hoje, use lookback_minutes=1440.
    - Para ontem ou desde ontem, use lookback_minutes=2880.
    - Se não houver período claro e a pergunta não pedir status atual, envie lookback_minutes=null.
    - Não envie campos fora do schema.

    Exemplo - status atual:
    Usuário: "O PIMS está normal agora?"
    Use:
    status_pims_tool({
        "pergunta_usuario": "O PIMS está normal agora?",
        "lookback_minutes": 60
    })

    Exemplo - últimas 2 horas:
    Usuário: "Verifique se teve erro na PI Web API nas últimas 2 horas."
    Use:
    status_pims_tool({
        "pergunta_usuario": "Verifique se teve erro na PI Web API nas últimas 2 horas.",
        "lookback_minutes": 120
    })

    Exemplo - sem período claro:
    Usuário: "Verifique problemas no PIMS."
    Use:
    status_pims_tool({
        "pergunta_usuario": "Verifique problemas no PIMS.",
        "lookback_minutes": null
    })

    Regras reforçadas pelos exemplos:
    - Esta tool é somente para status operacional do PIMS, PI Web API, servidores, serviços e logs.
    - O agente deve escolher lookback_minutes explicitamente.
    - A tool não infere período automaticamente.
    - Quando não houver período claro, use null.
    """

    result = await consultar_status_pims_service(
        user_message=pergunta_usuario or "",
        lookback_minutes=lookback_minutes,
        include_raw_response=False,
    )

    return result["output"]