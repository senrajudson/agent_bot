"""
PI System MCP Server

FastMCP server providing tools for querying PI System tags,
historical statistics, temporal calculus, and PIMS operational status.
"""

import asyncio
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mcp_server")

from fastmcp import FastMCP

from core.config import settings

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "PI System Tools",
    instructions=(
        "Tools for querying PI System tags via PI Web API. "
        "Use consultar_tag for current values and metadata. "
        "Use tag_statistics for historical aggregations (mean, max, min, sum, consumption). "
        "Use tag_calculus for temporal math (integral, derivative). "
        "Use status_pims_tool for PIMS operational status via Grafana/Loki logs."
    ),
)


# ---------------------------------------------------------------------------
# Tool: consultar_tag
# ---------------------------------------------------------------------------
@mcp.tool
async def consultar_tag(
    tags: list[str],
    pergunta_usuario: str | None = None,
) -> str:
    """
    Consulta valor atual, descrição, unidade de engenharia, tipo, digital set,
    locations, estados digitais e metadados de tags do PI System.

    Use quando o usuário pedir:
    - valor atual de uma tag
    - descrição, unidade, tipo da tag
    - digital set, estados digitais
    - instrumenttag, locations
    - metadados cadastrais de tags

    Args:
        tags: Lista de nomes de tags do PI System (preservar nomes exatos)
        pergunta_usuario: Pergunta original do usuário (para contexto)
    """
    from domain.pims.services.consultar_tag_service import consultar_tags_pi

    result = await consultar_tags_pi(
        tags=tags,
        pergunta_usuario=pergunta_usuario or "",
        include_raw_response=False,
    )
    return result["output"]


# ---------------------------------------------------------------------------
# Tool: tag_statistics
# ---------------------------------------------------------------------------
@mcp.tool
async def tag_statistics(
    tags: list[str],
    operation: str,
    start_time: str,
    end_time: str = "*",
    data_method: str = "summary",
    interval: str | None = None,
    summary_type: str | None = None,
    summary_duration: str | None = None,
    calculation_basis: str | None = None,
    context_text: str | None = None,
    max_count: int = 200000,
) -> str:
    """
    Executa estatísticas históricas de tags do PI System.

    Use quando o usuário pedir: média, máximo, mínimo, soma, contagem,
    mediana, amplitude, variância, desvio padrão, consumo total ou volume acumulado.

    Para consumo de vazão (Nm3/h): use data_method='summary',
    summary_type='Average', summary_duration='1h', calculation_basis='TimeWeighted',
    operation='sum'.

    Args:
        tags: Lista de tags do PI System
        operation: Operação estatística (mean, max, min, sum, count, etc.)
        start_time: Início do período (formato PI Web API: '*-7d', '2026-05-01T00:00:00')
        end_time: Fim do período ('*' = agora)
        data_method: Método temporal ('summary', 'recorded', 'interpolated')
        interval: Intervalo de amostragem (somente para 'interpolated')
        summary_type: Tipo de agregação (somente para 'summary'): Average, Maximum, Minimum, Total, Count, Range, StdDev
        summary_duration: Janela de agregação (somente para 'summary'): '1h', '30m', '1d'
        calculation_basis: Base de cálculo (somente para 'summary'): TimeWeighted, EventWeighted
        context_text: Texto original da pergunta do usuário
        max_count: Máximo de valores (somente para 'recorded')
    """
    from domain.analytics.services.math_tool_service import executar_estatistica_tags_service

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


# ---------------------------------------------------------------------------
# Tool: tag_calculus
# ---------------------------------------------------------------------------
@mcp.tool
async def tag_calculus(
    tags: list[str],
    operation: str,
    start_time: str,
    end_time: str = "*",
    data_method: str = "interpolated",
    interval: str | None = None,
    summary_type: str | None = None,
    summary_duration: str | None = None,
    calculation_basis: str | None = None,
    time_unit: str = "none",
    context_text: str | None = None,
    max_count: int = 200000,
) -> str:
    """
    Executa cálculos matemáticos temporais sobre curvas de tags do PI System.

    Use quando o usuário pedir explicitamente: integral, derivada,
    taxa de variação, variação por segundo/minuto/hora, área sob a curva.

    Args:
        tags: Lista de tags do PI System
        operation: 'integral' ou 'derivative'
        start_time: Início do período (formato PI Web API)
        end_time: Fim do período ('*' = agora)
        data_method: Método temporal ('interpolated', 'recorded', 'summary')
        interval: Intervalo de amostragem (somente para 'interpolated')
        summary_type: Tipo de agregação (somente para 'summary')
        summary_duration: Janela de agregação (somente para 'summary')
        calculation_basis: Base de cálculo (somente para 'summary')
        time_unit: Unidade temporal do cálculo: 'second', 'minute', 'hour', 'none'
        context_text: Texto original da pergunta do usuário
        max_count: Máximo de valores (somente para 'recorded')
    """
    from domain.analytics.services.math_tool_service import executar_calculo_historico_service

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


# ---------------------------------------------------------------------------
# Tool: status_pims_tool
# ---------------------------------------------------------------------------
@mcp.tool
async def status_pims_tool(
    pergunta_usuario: str | None = None,
    lookback_minutes: int | None = None,
) -> str:
    """
    Consulta logs do Grafana/Loki para avaliar status, saúde, erro, lentidão,
    queda, indisponibilidade ou instabilidade do PIMS, PI Web API, servidores
    e serviços monitorados.

    Use quando o usuário perguntar sobre: status do PIMS, erros, lentidão,
    indisponibilidade, timeout, erro 500/503, saúde do ambiente.

    Args:
        pergunta_usuario: Texto original da pergunta do usuário
        lookback_minutes: Minutos para consultar nos logs (60=status atual, 120=2h, 1440=hoje, null=sem período claro)
    """
    from domain.pims_ops.services.status_pims_service import consultar_status_pims_service

    result = await consultar_status_pims_service(
        user_message=pergunta_usuario or "",
        lookback_minutes=lookback_minutes,
        include_raw_response=False,
    )
    return result["output"]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from core.startup_checks import check_math_tool

    logger.info(
        "Starting MCP Server on %s:%s (Math Tool: %s)",
        settings.MCP_HOST,
        settings.MCP_PORT,
        settings.MATH_TOOL_BASE_URL,
    )

    asyncio.run(check_math_tool(settings.MATH_TOOL_BASE_URL))

    mcp.run(transport="http", host=settings.MCP_HOST, port=settings.MCP_PORT)
