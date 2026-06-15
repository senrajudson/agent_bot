from langchain_core.tools import tool
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.math_tool import (
    CalculationBasis,
    CalculusOperation,
    SummaryType,
    TemporalDataMethod,
    TimeUnit,
)
from app.services.math_tool_service import executar_calculo_historico_service


class TagCalculusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str] = Field(
        description=(
            "Lista de tags do PI System usadas no cálculo temporal. "
            "Preserve exatamente os nomes das tags informadas pelo usuário. "
            "Nunca altere, abrevie, traduza ou escape underscores das tags."
        )
    )

    operation: CalculusOperation = Field(
        description=(
            "Operação temporal matemática explícita sobre a curva de dados. "
            "Use 'integral' para integralização, área acumulada ou total integrado no tempo. "
            "Use 'derivative' para derivada, taxa de variação, variação por unidade de tempo. "
            "Esta tool é para cálculos matemáticos temporais explicitamente solicitados."
        )
    )

    start_time: str = Field(
        description=(
            "Início do período em formato PI Web API. "
            "Relativos: '*-2h' (2h atrás), '*-1d' (1 dia atrás). "
            "Absolutos: '2026-05-01T00:00:00', '2026-06-15T08:00:00Z'."
        )
    )

    end_time: str = Field(
        default="*",
        description="Fim do período. Use '*' para agora.",
    )

    data_method: TemporalDataMethod = Field(
        description="Método de consulta temporal.",
    )

    interval: str | None = Field(
        default=None,
        description=(
            "Intervalo de amostragem, usado somente quando data_method='interpolated'. "
            "Não é time_unit e não é summary_duration. "
            "Quando data_method='recorded' ou 'summary', envie null."
        ),
    )

    summary_type: SummaryType | None = Field(
        default=None,
        description=(
            "Tipo de agregação, usado somente quando data_method='summary'. "
            "Quando data_method='recorded' ou 'interpolated', envie null."
        ),
    )

    summary_duration: str | None = Field(
        default=None,
        description=(
            "Janela de agregação, usada somente quando data_method='summary'. "
            "Não confunda summary_duration com interval. "
            "Quando data_method='recorded' ou 'interpolated', envie null."
        ),
    )

    calculation_basis: CalculationBasis | None = Field(
        default=None,
        description=(
            "Base de cálculo, usada somente quando data_method='summary'. "
            "Quando data_method='recorded' ou 'interpolated', envie null."
        ),
    )

    time_unit: TimeUnit = Field(
        default="none",
        description=(
            "Unidade temporal usada no cálculo matemático da integral ou derivada. "
            "Para derivative: use 'second', 'minute' ou 'hour' conforme o usuário pedir. "
            "Para integral de grandezas em unidade/hora (Nm3/h, m3/h, kg/h), use 'hour'. "
            "time_unit é unidade de cálculo, não unidade de engenharia da tag. "
            "Use 'none' quando não houver unidade temporal aplicável."
        ),
    )

    context_text: str | None = Field(
        default=None,
        description=(
            "Texto original da pergunta do usuário. "
            "Use para preservar a intenção da solicitação."
        ),
    )

    max_count: int = Field(
        default=200000,
        description="Quantidade máxima de valores, usado somente quando data_method='recorded'.",
    )


@tool(args_schema=TagCalculusInput)
async def tag_calculus_tool(
    tags: list[str],
    operation: CalculusOperation,
    start_time: str,
    end_time: str = "*",
    data_method: TemporalDataMethod = "interpolated",
    interval: str | None = None,
    summary_type: SummaryType | None = None,
    summary_duration: str | None = None,
    calculation_basis: CalculationBasis | None = None,
    time_unit: TimeUnit = "none",
    context_text: str | None = None,
    max_count: int = 200000,
) -> str:
    """
    Executa cálculos matemáticos temporais sobre curvas de tags do PI System.

    Use esta tool quando o usuário pedir explicitamente:
    - integral, integralização, área acumulada
    - derivada, taxa de variação
    - variação por segundo, por minuto ou por hora

    Exemplos de intenção que usam esta tool:
    - "calcule a integral da tag X"
    - "qual a derivada da tag Y"
    - "taxa de variação por minuto da tag Z"
    - "área sob a curva da tag W"

    Contrato:
    - Sempre envie todos os campos do schema.
    - Quando um campo não se aplicar ao data_method, envie null.
    - Não envie campos fora do schema.
    - time_unit é unidade temporal de cálculo, não unidade de engenharia.
    - interval é frequência de amostragem, não time_unit.
    """

    result = await executar_calculo_historico_service(
        tags=tags,
        operation=operation,
        start_time=start_time,
        end_time=end_time,
        interval=interval,
        time_unit=time_unit,
        context_text=context_text or "",
        max_count=max_count,
        data_method=data_method,
        summary_type=summary_type,
        summary_duration=summary_duration,
        calculation_basis=calculation_basis,
    )

    return result["output"]
