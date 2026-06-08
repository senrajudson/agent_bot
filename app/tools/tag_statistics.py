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
            "Operação estatística final executada pela calculadora sobre os valores retornados. "
            "Não confunda operation com summary_type. "
            "operation é o cálculo final feito pela aplicação. "
            "summary_type é o cálculo feito pela PI Web API dentro de cada janela temporal. "
            "Use mean para média final, max para máximo, min para mínimo, sum para soma final, "
            "count para contagem, median para mediana, range para amplitude, "
            "variance_population ou variance_sample para variância, "
            "stddev_population ou stddev_sample para desvio padrão. "
            "Para consumo total, volume acumulado ou acumulado de vazão calculado por médias horárias, "
            "use operation='sum'."
        )
    )

    start_time: str = Field(
        description=(
            "Início do período em formato aceito pela PI Web API. "
            "Exemplos relativos: '*-2h', '*-30m', '*-1d'. "
            "Exemplos absolutos: '2026-05-01T00:00:00', '2026-05-23T08:00:00Z'. "
            "Para períodos mensais resolvidos, use sempre data e hora completas."
        )
    )

    end_time: str = Field(
        default="*",
        description=(
            "Fim do período em formato aceito pela PI Web API. "
            "Use '*' para agora. "
            "Para períodos fechados, use data e hora completas. "
            "Para mês completo, prefira o primeiro instante do próximo período. "
            "Exemplo para maio de 2026: start_time='2026-05-01T00:00:00' "
            "e end_time='2026-06-01T00:00:00'."
        ),
    )

    data_method: TemporalDataMethod = Field(
        description=(
            "Método de consulta temporal da PI Web API. "
            "Use recorded somente para histórico bruto, valores reais gravados, eventos, "
            "mudanças de estado e tags digitais históricas. "
            "Não use recorded para consumo, volume acumulado, soma mensal, média mensal "
            "ou estatísticas agregadas de períodos longos. "
            "Use interpolated quando houver intervalo de amostragem explícito, como 1m, 5m, 10m ou 1h. "
            "Use summary para agregações por período ou janela, como média, máximo, mínimo, soma, "
            "contagem, consumo total, volume acumulado ou resumo de períodos longos."
        ),
    )

    interval: str | None = Field(
        default=None,
        description=(
            "Intervalo usado somente quando data_method='interpolated'. "
            "Exemplos: '1m', '5m', '10m', '1h'. "
            "interval é frequência de amostragem, não é janela de summary. "
            "Quando data_method='recorded' ou data_method='summary', envie null."
        ),
    )

    summary_type: SummaryType | None = Field(
        default=None,
        description=(
            "Tipo de agregação da PI Web API usado somente quando data_method='summary'. "
            "Valores possíveis: Average, Maximum, Minimum, Total, Count, Range, StdDev. "
            "summary_type calcula cada janela temporal antes da operation final. "
            "Não confunda summary_type com operation. "
            "Para consumo total de vazão, volume acumulado ou acumulado de vazão, use Average. "
            "Quando data_method='recorded' ou data_method='interpolated', envie null."
        ),
    )

    summary_duration: str | None = Field(
        default=None,
        description=(
            "Janela de agregação usada somente quando data_method='summary'. "
            "Exemplos: '1h', '30m', '1d'. "
            "Para consumo total de vazão por média horária, use '1h'. "
            "Não confunda summary_duration com interval. "
            "Quando data_method='recorded' ou data_method='interpolated', envie null."
        ),
    )

    calculation_basis: CalculationBasis | None = Field(
        default=None,
        description=(
            "Base de cálculo usada somente quando data_method='summary'. "
            "Use TimeWeighted para variáveis contínuas de processo, como vazão, pressão, temperatura e nível. "
            "Use EventWeighted quando cada evento gravado deve ter o mesmo peso. "
            "Nunca use Volume como calculation_basis. "
            "Quando data_method='recorded' ou data_method='interpolated', envie null."
        ),
    )

    context_text: str | None = Field(
        default=None,
        description="Texto original da pergunta do usuário.",
    )

    max_count: int = Field(
        default=200000,
        description="Quantidade máxima de valores quando data_method='recorded'.",
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
    """
    Executa estatísticas históricas de tags do PI System.

    Use esta tool quando o usuário pedir cálculo histórico de tags, como:
    média, máximo, mínimo, soma, contagem, mediana, amplitude, variância,
    desvio padrão, consumo total, volume acumulado ou acumulado de vazão.

    Contrato padronizado:
    - Sempre envie todos os campos do schema.
    - Quando um campo não se aplicar ao data_method escolhido, envie null.
    - Não envie campos fora do schema.
    - recorded: usa valores reais gravados. Envie interval, summary_type,
      summary_duration e calculation_basis como null.
    - interpolated: exige interval. Envie summary_type, summary_duration
      e calculation_basis como null.
    - summary: exige summary_type, summary_duration e calculation_basis.
      Envie interval como null.

    Exemplo - consumo total de vazão em período mensal:
    Usuário: "Qual foi o consumo total da tag ACI_LC1_MC_MACARICOS_GC_VAZ_O2 em abril?"
    Use:
    tag_statistics_tool({
        "tags": ["ACI_LC1_MC_MACARICOS_GC_VAZ_O2"],
        "operation": "sum",
        "start_time": "2026-04-01T00:00:00",
        "end_time": "2026-05-01T00:00:00",
        "data_method": "summary",
        "interval": null,
        "summary_type": "Average",
        "summary_duration": "1h",
        "calculation_basis": "TimeWeighted",
        "context_text": "Qual foi o consumo total da tag ACI_LC1_MC_MACARICOS_GC_VAZ_O2 em abril?",
        "max_count": 200000
    })

    Exemplo - máximo histórico em período:
    Usuário: "Qual foi o maior valor da tag TEMP_FORNO_01 ontem?"
    Use:
    tag_statistics_tool({
        "tags": ["TEMP_FORNO_01"],
        "operation": "max",
        "start_time": "t-1d",
        "end_time": "t",
        "data_method": "summary",
        "interval": null,
        "summary_type": "Maximum",
        "summary_duration": "1h",
        "calculation_basis": "TimeWeighted",
        "context_text": "Qual foi o maior valor da tag TEMP_FORNO_01 ontem?",
        "max_count": 200000
    })

    Regras reforçadas pelos exemplos:
    - Sempre envie todos os campos do schema.
    - Use null nos campos que não se aplicam ao data_method escolhido.
    - Consumo total, volume acumulado e acumulado de vazão usam summary, nunca recorded.
    - Para consumo total de vazão, use operation="sum", summary_type="Average", summary_duration="1h" e calculation_basis="TimeWeighted".
    - recorded é somente para valores reais gravados, eventos, mudanças de estado e histórico bruto.
    - interpolated é usado quando o usuário pedir explicitamente uma amostragem fixa, como 1m, 5m, 10m ou 1h.
    - summary sempre exige summary_type, summary_duration, calculation_basis e interval=null.
    """

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