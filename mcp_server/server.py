"""
PI System MCP Server

FastMCP server providing tools for querying PI System tags,
historical statistics, temporal calculus, and PIMS operational status.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from typing import Any

from fastmcp import FastMCP

from core.config import settings

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "PI System Tools",
    instructions=(
        "Tools for querying PI System tags via PI Web API. "
        "Use pi_request for any PI Web API call: tag lookup, search, value, "
        "metadata, attributes, streams, digital states, and batch. "
        "Use tag_statistics for historical aggregations (mean, max, min, sum, consumption). "
        "Use tag_calculus for temporal math (integral, derivative). "
        "Use status_pims for PIMS operational status via Grafana/Loki logs."
    ),
)


# ---------------------------------------------------------------------------
# Tool: pi_request (generic PI Web API caller)
# ---------------------------------------------------------------------------
@mcp.tool
async def pi_request(
    method: str,
    path_template: str,
    path_params: dict[str, str] | None = None,
    query_params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    context_text: str | None = None,
) -> str:
    """
    Generic PI Web API caller for any endpoint documented in the guide.

    Use for:
    - Tag lookup: GET /points?path=\\PIMS\\TAG_NAME
    - Tag search: GET /dataservers/{PIMS_DATASERVER_WEBID}/points with
      nameFilter, descriptorFilter, or instrumenttagFilter
    - Current value: GET /streams/{WebId}/value
    - Metadata: GET /points?path=... with selectedFields
    - Attributes: GET /points/{WebId}/attributes?name=...
    - Recorded/interpolated/summary streams
    - Digital states: GET /enumerationsets/{WebId}/enumerationvalues
    - Batch requests: POST /batch

    Path templates (whitelist):
      IMPORTANTE: path_template recebe SOMENTE o path (sem método).
      O método HTTP vai no campo "method".
      Exemplo: path_template="/streams/{WebId}/value", method="GET".

      /points
      /points/{WebId}
      /points/{WebId}/attributes
      /streams/{WebId}/value
      /streams/{WebId}/recorded
      /streams/{WebId}/interpolated
      /streams/{WebId}/summary
      /streams/{WebId}/plot
      /dataservers
      /dataservers/{WebId}/points
      /dataservers/{WebId}/enumerationsets
      /enumerationsets/{WebId}/enumerationvalues
      /streamsets/value
      /streamsets/recorded
      /streamsets/interpolated
      /batch

    Path placeholders:
      {WebId} — point or data server WebId (discovered via prior call)
      PIMS_DATASERVER_WEBID — auto-resolved for /dataservers/{WebId}/points

    Args:
        method: HTTP method ("GET" or "POST")
        path_template: One of the whitelisted path templates above
        path_params: Dict of path placeholders to resolve (e.g. {"WebId": "P0DPm..."})
        query_params: Query string parameters (e.g. {"path": "\\PIMS\\TAG"})
        json_body: Request body for POST /batch
        context_text: Original user question (for tracing/logging)
    """
    from clients.pi_web_api_client import pi_request as _pi_request

    result = await _pi_request(
        method=method,
        path_template=path_template,
        path_params=path_params,
        query_params=query_params,
        json_body=json_body,
    )

    import json
    return json.dumps(result, ensure_ascii=False, default=str)


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
    Shortcut for historical statistics — internally uses /points + /streams/{webId}/summary.

    Use when the user asks for: mean, max, min, sum, count, consumption,
    median, range, variance, stddev. For consumption of flow tags (Nm3/h):
    data_method='summary', summary_type='Average', summary_duration='1h',
    calculation_basis='TimeWeighted', operation='sum'.

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
    from services.math_tool_service import executar_estatistica_tags_service

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
    Shortcut for temporal calculus — internally uses /points + /streams/{webId}/interpolated.

    Use when the user explicitly asks for: integral, derivative, rate of change,
    area under curve, second/minute/hour variation.

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
    from services.math_tool_service import executar_calculo_historico_service

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
# Tool: status_pims
# ---------------------------------------------------------------------------
@mcp.tool
async def status_pims(
    pergunta_usuario: str | None = None,
    lookback_minutes: int | None = None,
) -> str:
    """
    Consulta logs do Grafana/Loki para avaliar status, saúde, erro, lentidão,
    queda, indisponibilidade ou instabilidade do PIMS, PI Web API, servidores
    e serviços monitorados.

    Use when the user asks about: PIMS status, errors, slowness,
    downtime, timeout, HTTP 500/503, environment health.

    Args:
        pergunta_usuario: Texto original da pergunta do usuário
        lookback_minutes: Minutos para consultar nos logs (60=status atual, 120=2h, 1440=hoje, null=sem período claro)
    """
    from services.status_pims_service import consultar_status_pims_service

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
    mcp.run(transport="http", host=settings.MCP_HOST, port=settings.MCP_PORT)
