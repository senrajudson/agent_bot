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
            "Operação temporal final. "
            "Use integral quando o usuário pedir integralização, integral no tempo, "
            "área acumulada, acumulado por integração ou total integrado no tempo. "
            "Use derivative quando o usuário pedir derivada, taxa de variação, "
            "variação por hora, variação por minuto, velocidade de mudança ou tendência temporal. "
            "Não use esta tool para média, máximo, mínimo, soma simples, contagem, mediana, "
            "desvio padrão, variância ou amplitude; nesses casos use tag_statistics_tool."
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
            "Use recorded somente quando o usuário pedir histórico bruto, valores reais gravados, "
            "eventos reais, mudanças de estado ou tags digitais históricas. "
            "Use interpolated quando o cálculo precisar de série em intervalo fixo, principalmente "
            "para integralização ou derivada com amostragem controlada. "
            "Use summary quando o cálculo temporal deve ser feito sobre agregações por janela, "
            "como médias horárias antes da integralização. "
            "Não confunda data_method com operation."
        ),
    )

    interval: str | None = Field(
        default=None,
        description=(
            "Intervalo usado somente quando data_method='interpolated'. "
            "Exemplos: '1m', '5m', '10m', '1h'. "
            "interval é a frequência de amostragem dos dados. "
            "interval não é time_unit e não é summary_duration. "
            "Quando data_method='recorded' ou data_method='summary', envie null."
        ),
    )

    summary_type: SummaryType | None = Field(
        default=None,
        description=(
            "Tipo de agregação usado somente quando data_method='summary'. "
            "Valores possíveis: Average, Maximum, Minimum, Total, Count, Range, StdDev. "
            "summary_type é o cálculo feito pela PI Web API dentro de cada janela temporal. "
            "Para integralização baseada em médias horárias de vazão, use Average. "
            "Quando data_method='recorded' ou data_method='interpolated', envie null."
        ),
    )

    summary_duration: str | None = Field(
        default=None,
        description=(
            "Janela de agregação usada somente quando data_method='summary'. "
            "Exemplos: '1h', '30m', '1d'. "
            "Para média horária antes de integralização, use '1h'. "
            "summary_duration não é interval. "
            "Quando data_method='recorded' ou data_method='interpolated', envie null."
        ),
    )

    calculation_basis: CalculationBasis | None = Field(
        default=None,
        description=(
            "Base de cálculo usada somente quando data_method='summary'. "
            "Use TimeWeighted para variáveis contínuas de processo, como vazão, temperatura, "
            "pressão, nível e concentração. "
            "Use EventWeighted quando cada evento gravado deve ter o mesmo peso. "
            "Nunca use Volume como calculation_basis. "
            "Quando data_method='recorded' ou data_method='interpolated', envie null."
        ),
    )

    time_unit: TimeUnit = Field(
        default="none",
        description=(
            "Unidade temporal usada no cálculo final. "
            "Para derivative, use second, minute ou hour conforme o usuário pedir taxa por segundo, "
            "por minuto ou por hora. "
            "Para integral de grandezas em unidade por hora, como Nm3/h, m3/h, kg/h ou t/h, "
            "use hour. "
            "Para integral de grandezas em unidade por minuto, use minute. "
            "Para integral de grandezas em unidade por segundo, use second. "
            "time_unit não é interval. "
            "Use none quando não houver unidade temporal aplicável ou quando o usuário não informar contexto suficiente."
        ),
    )

    context_text: str | None = Field(
        default=None,
        description=(
            "Texto original da pergunta do usuário. "
            "Use para preservar a intenção da solicitação e ajudar na rastreabilidade da chamada."
        ),
    )

    max_count: int = Field(
        default=200000,
        description="Quantidade máxima de valores quando data_method='recorded'.",
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
    Executa integralização, derivada ou taxa de variação temporal de tags do PI System.

    Use esta tool quando o usuário pedir:
    - integralização de tag;
    - integral no tempo;
    - área acumulada;
    - total integrado;
    - derivada;
    - taxa de variação;
    - variação por segundo, por minuto ou por hora;
    - velocidade de mudança de uma variável de processo.

    Não use esta tool para:
    - média, máximo, mínimo, soma simples, contagem, mediana, amplitude,
      variância ou desvio padrão;
    - valor atual, descrição, unidade, tipo, digital set ou metadados de tag;
    - status do PIMS, PI Web API, servidores ou serviços.

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
    - time_unit é a unidade temporal do cálculo final, não a frequência de amostragem.
    - interval é frequência de amostragem.
    - summary_duration é janela de agregação da PI Web API.

    Exemplo - integralização usando série interpolada:
    Usuário: "Integre a tag VAZAO_LINHA_01 nas últimas 6 horas usando pontos a cada 5 minutos."
    Use:
    tag_calculus_tool({
        "tags": ["VAZAO_LINHA_01"],
        "operation": "integral",
        "start_time": "*-6h",
        "end_time": "*",
        "data_method": "interpolated",
        "interval": "5m",
        "summary_type": null,
        "summary_duration": null,
        "calculation_basis": null,
        "time_unit": "hour",
        "context_text": "Integre a tag VAZAO_LINHA_01 nas últimas 6 horas usando pontos a cada 5 minutos.",
        "max_count": 200000
    })

    Exemplo - derivada por minuto:
    Usuário: "Calcule a variação por minuto da tag PRESSAO_LINHA_01 nos últimos 30 minutos."
    Use:
    tag_calculus_tool({
        "tags": ["PRESSAO_LINHA_01"],
        "operation": "derivative",
        "start_time": "*-30m",
        "end_time": "*",
        "data_method": "interpolated",
        "interval": "1m",
        "summary_type": null,
        "summary_duration": null,
        "calculation_basis": null,
        "time_unit": "minute",
        "context_text": "Calcule a variação por minuto da tag PRESSAO_LINHA_01 nos últimos 30 minutos.",
        "max_count": 200000
    })

    Exemplo - cálculo temporal com histórico bruto gravado:
    Usuário: "Calcule a derivada usando os valores gravados reais da tag NIVEL_TQ_01 hoje."
    Use:
    tag_calculus_tool({
        "tags": ["NIVEL_TQ_01"],
        "operation": "derivative",
        "start_time": "t",
        "end_time": "*",
        "data_method": "recorded",
        "interval": null,
        "summary_type": null,
        "summary_duration": null,
        "calculation_basis": null,
        "time_unit": "hour",
        "context_text": "Calcule a derivada usando os valores gravados reais da tag NIVEL_TQ_01 hoje.",
        "max_count": 200000
    })

    Regras reforçadas pelos exemplos:
    - Sempre envie todos os campos do schema.
    - Use null nos campos que não se aplicam ao data_method escolhido.
    - Use operation="integral" para integralização, integral no tempo, área acumulada ou total integrado.
    - Use operation="derivative" para derivada, taxa de variação, variação por minuto, por hora ou por segundo.
    - Para integralização de vazão em unidade por hora, use time_unit="hour".
    - Para taxa de variação por hora, use time_unit="hour".
    - Para taxa de variação por minuto, use time_unit="minute".
    - Para taxa de variação por segundo, use time_unit="second".
    - Use interpolated quando precisar de série em intervalo fixo.
    - Use recorded somente para histórico bruto, valores gravados reais, eventos ou mudanças de estado.
    - Use summary quando quiser calcular sobre agregações por janela, como médias horárias antes da integralização.
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