from langchain_core.tools import tool
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.math_tool import (
    CalculationBasis,
    StatsOperation,
    SummaryType,
    TemporalDataMethod,
)
from app.services.math_tool_service import executar_estatistica_tags_service


class TagStatisticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str] = Field(
        description=(
            "Lista de tags do PI System usadas na estatística. "
            "Preserve exatamente os nomes das tags informadas pelo usuário. "
            "Nunca altere, abrevie, traduza ou escape underscores das tags."
        )
    )

    operation: StatsOperation = Field(
        description=(
            "Operação estatística final executada sobre os valores retornados pela consulta temporal. "
            "operation é o cálculo final feito pela aplicação após obter os dados. "
            "summary_type é o cálculo feito pela PI Web API dentro de cada janela temporal. "
            "Exemplos: mean para média final, max para máximo, min para mínimo, "
            "sum para soma total dos valores retornados, count para contagem. "
            "Para consumo total de vazão (Nm3/h), use operation='sum' com data_method='summary' "
            "e summary_type='Average'."
        )
    )

    start_time: str = Field(
        description=(
            "Início do período em formato PI Web API. "
            "Relativos: '*-2h' (2h atrás), '*-1d' (1 dia atrás), '*-7d' (7 dias atrás). "
            "Absolutos: '2026-05-01T00:00:00', '2026-06-15T08:00:00Z'. "
            "Para mês fechado, use início do mês: '2026-05-01T00:00:00-03:00'."
        )
    )

    end_time: str = Field(
        default="*",
        description=(
            "Fim do período. Use '*' para agora. "
            "Para mês fechado, use início do próximo mês: '2026-06-01T00:00:00-03:00'."
        ),
    )

    data_method: TemporalDataMethod = Field(
        description=(
            "Método de consulta temporal da PI Web API. "
            "Use 'summary' para agregações por período: média, máximo, mínimo, soma, "
            "contagem, consumo total, volume acumulado, resumo de períodos longos. "
            "Use 'recorded' para histórico bruto, eventos reais gravados, mudanças de estado. "
            "Use 'interpolado' quando houver intervalo de amostragem explícito (ex: 1m, 5m, 1h)."
        ),
    )

    interval: str | None = Field(
        default=None,
        description=(
            "Intervalo de amostragem, usado somente quando data_method='interpolated'. "
            "Não é janela de summary. Quando data_method='recorded' ou 'summary', envie null."
        ),
    )

    summary_type: SummaryType | None = Field(
        default=None,
        description=(
            "Tipo de agregação da PI Web API, usado somente quando data_method='summary'. "
            "summary_type calcula cada janela temporal antes da operation final. "
            "Para consumo total de vazão em Nm3/h, use summary_type='Average'. "
            "Quando data_method='recorded' ou 'interpolated', envie null."
        ),
    )

    summary_duration: str | None = Field(
        default=None,
        description=(
            "Janela de agregação, usada somente quando data_method='summary'. "
            "Exemplo: '1h' para médias horárias, '30m' para médias de 30 minutos. "
            "Para consumo total de vazão por média horária, use '1h'. "
            "Não confunda summary_duration com interval. "
            "Quando data_method='recorded' ou 'interpolated', envie null."
        ),
    )

    calculation_basis: CalculationBasis | None = Field(
        default=None,
        description=(
            "Base de cálculo, usada somente quando data_method='summary'. "
            "Use TimeWeighted para variáveis contínuas de processo (vazão, temperatura, pressão, nível). "
            "Use EventWeighted quando cada evento gravado deve ter o mesmo peso. "
            "Para consumo de vazão em Nm3/h, use TimeWeighted. "
            "Quando data_method='recorded' ou 'interpolated', envie null."
        ),
    )

    context_text: str | None = Field(
        default=None,
        description="Texto original da pergunta do usuário.",
    )

    max_count: int = Field(
        default=200000,
        description="Quantidade máxima de valores, usado somente quando data_method='recorded'.",
    )


@tool(args_schema=TagStatisticsInput)
async def tag_statistics_tool(
    tags: list[str],
    operation: StatsOperation,
    start_time: str,
    end_time: str = "*",
    data_method: TemporalDataMethod = "summary",
    interval: str | None = None,
    summary_type: SummaryType | None = None,
    summary_duration: str | None = None,
    calculation_basis: CalculationBasis | None = None,
    context_text: str | None = None,
    max_count: int = 200000,
) -> str:
    """Executa estatísticas históricas de tags do PI System."""
    if data_method == "summary":
        summary_type = summary_type or "Average"
        summary_duration = summary_duration or "1h"
        calculation_basis = calculation_basis or "TimeWeighted"

    result = await executar_estatistica_tags_service(
        tags=tags,
        operation=operation,
        start_time=start_time,
        end_time=end_time,
        interval=interval,
        max_count=max_count,
        data_method=data_method,
        summary_type=summary_type,
        summary_duration=summary_duration,
        calculation_basis=calculation_basis,
    )

    return result["output"]
