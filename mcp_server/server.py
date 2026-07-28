"""
PI System MCP Server

FastMCP server providing tools for querying PI System tags,
historical statistics, temporal calculus, and PIMS operational status.
"""

import asyncio
import json
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
from fastmcp.exceptions import ToolError

from core.config import settings

from domain.core.config import configure_domain_settings
from domain.shared.schemas.math_tool import GroupBy

configure_domain_settings(settings.to_domain_integration_settings())

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "PI System Tools",
    instructions=(
        "Roteamento: valor atual/metadados/timestamp → consultar_tag; "
        "descoberta de tags por nome/descrição/área → search_pi_points; "
        "atributos de configuração do PI Point (compressão/exceção/scan) "
        "→ tag_attributes_tool; estatísticas históricas (média/máx/mín/soma) "
        "→ tag_statistics_tool; cálculo temporal (integral/derivada/variação) "
        "→ tag_calculus_tool; status operacional do PIMS → status_pims_tool. "
        "Desambiguação: estatística simples → tag_statistics_tool; "
        "integral/derivada explícita → tag_calculus_tool. "
        "Valor atual → consultar_tag; atributos de configuração → tag_attributes_tool. "
        "Política: search_pi_points no máximo 2 vezes por turno; 2ª só com query diferente e se 1ª foi fraca; 3ª bloqueada."
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
    Consulta valor atual, descrição, unidade, tipo, digital set, instrumenttag,
    locations e metadados de tags do PI System.

    Use quando o usuário pedir valor atual, último valor, descrição, tipo,
    digital set, instrumenttag, locations ou metadados cadastrais de uma tag
    já conhecida.

    Args:
        tags: Lista de nomes de tags do PI System (preservar nomes exatos).
        pergunta_usuario: Pergunta original (opcional, contexto).
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
    group_by: GroupBy | None = "1h",
    return_series: bool = False,
) -> str:
    """
    Executa estatísticas históricas (média, máximo, mínimo, soma, consumo, etc.)
    de tags do PI System em um período.

    Use quando o usuário pedir estatísticas históricas, consumo, soma, média,
    máximo, mínimo, contagem, mediana, variância ou desvio padrão.

    Para consumo de vazão (Nm3/h): use data_method='summary',
    summary_type='Average', summary_duration='1h',
    calculation_basis='TimeWeighted', operation='sum'.

    Para consumo discriminado, use group_by='1m','1h','1d','1w','1mo' e return_series=True.

    Args:
        tags: Lista de tags.
        operation: Operação estatística (mean, max, min, sum, count, etc.).
        start_time: Início do período (formato PI Web API).
        end_time: Fim do período ('*' = agora).
        data_method: 'summary', 'recorded', 'interpolated'.
        interval: Resolução da consulta interpolada (ex: '1m', '5m'). `interval` e `group_by` são parâmetros distintos: `interval` controla a coleta; `group_by` controla a agregação. Ambos podem receber '1m' com semânticas diferentes.
        summary_type: 'Average', 'Maximum', 'Minimum', 'Total', 'Count', 'Range', 'StdDev'.
        summary_duration: Janela ('1h', '30m', '1d').
        calculation_basis: 'TimeWeighted' ou 'EventWeighted'.
        context_text: Pergunta original (opcional).
        max_count: Limite de valores (somente 'recorded').
        group_by: Granularidade dos buckets estatísticos. Aceita '1m','1h','1d','1w','1mo'. Default='1h'. A inferência a partir da linguagem natural é responsabilidade do agente.
        return_series: Se True, retorna lista de valores por período.
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
        group_by=group_by or "1h",
        return_series=return_series,
    )

    if result.get("status") in ("invalid_argument", "internal_error"):
        error_code = result.get("error_code", "UNKNOWN")
        message = result.get("output", "Erro interno inesperado.")
        if result.get("status") == "internal_error":
            message = "Erro interno inesperado. Tente novamente."
        raise ToolError(f"[{error_code}] {message}")

    if result.get("status") in ("no_data", "insufficient_data"):
        return json.dumps(result.get("tool_result", {}), ensure_ascii=False)

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
    Executa cálculos matemáticos temporais (integral, derivada, taxa de variação)
    sobre curvas de tags do PI System.

    Use quando o usuário pedir explicitamente: integral, derivada, taxa de
    variação, variação por segundo/minuto/hora, área sob a curva.

    Args:
        tags: Lista de tags.
        operation: 'integral' ou 'derivative'.
        start_time: Início do período.
        end_time: Fim do período ('*' = agora).
        data_method: 'interpolated', 'recorded', 'summary'.
        interval: Intervalo (somente 'interpolated').
        summary_type: 'Average', etc. (somente 'summary').
        summary_duration: Janela (somente 'summary').
        calculation_basis: 'TimeWeighted' ou 'EventWeighted' (somente 'summary').
        time_unit: 'second', 'minute', 'hour', 'none'.
        context_text: Pergunta original (opcional).
        max_count: Limite (somente 'recorded').
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
    Consulta logs do Grafana/Loki para avaliar status operacional do PIMS.

    Use quando o usuário perguntar sobre: status do PIMS, saúde do ambiente,
    erros, lentidão, indisponibilidade, timeout, erro 500/503, instabilidade
    em servidores. Também verifica conectividade do DataServer configurado
    na PI Web API via /dataservers.

    Args:
        pergunta_usuario: Pergunta original do usuário (opcional).
        lookback_minutes: Janela em minutos (60=atual, 120=2h, 1440=hoje).
    """
    from domain.pims_ops.services.status_pims_service import consultar_status_pims_service

    result = await consultar_status_pims_service(
        user_message=pergunta_usuario or "",
        lookback_minutes=lookback_minutes,
        include_raw_response=False,
    )
    return result["output"]


# ---------------------------------------------------------------------------
# Tool: tag_attributes_tool
# ---------------------------------------------------------------------------
@mcp.tool
async def tag_attributes_tool(
    tag: str,
    attribute_group: str = "auto",
    attributes: list[str] | None = None,
) -> str:
    """
    Consulta atributos de configuração de uma tag PI via /points/{webId}/attributes.

    Use quando o usuário perguntar sobre: compressão (compdev, compmin, compmax,
    compressing), exceção (excdev, excmin, excmax), scan, archiving, pointsource,
    instrumenttag, location ou outros atributos cadastrais do PI Point.

    NÃO usar para valor atual da tag — para isso, use consultar_tag.

    Args:
        tag: Nome exato da tag (preservar underscores).
        attribute_group: 'auto' | 'compression' | 'exception' | 'archive' |
                         'identity' | 'scaling' | 'interface' | 'security' | 'all'.
        attributes: Lista explícita de atributos (sobrepõe attribute_group).
    """
    try:
        from domain.pims.services.tag_attributes_service import (
            get_tag_attributes,
        )

        result = await get_tag_attributes(
            tag=tag,
            attribute_group=attribute_group,
            attributes=attributes,
        )
        return result["output"]
    except ValueError as e:
        return f"Erro: {e}"


# ---------------------------------------------------------------------------
# Tool: search_pi_points
# ---------------------------------------------------------------------------
@mcp.tool
async def search_pi_points(
    query: str,
    max_count: int = 20,
    search_mode: str = "auto",
) -> str:
    """
    Busca tags/PI Points no PI Server por nome, descrição ou query textual.

    Use quando o usuário pedir para localizar, procurar, encontrar ou listar
    tags relacionadas a um termo, equipamento, área, variável ou descrição.

    Args:
        query: Termo de busca (parte do nome, descrição, equipamento, etc.).
        max_count: Máximo de resultados (default 20, máximo 100).
        search_mode: 'auto', 'name', 'description', 'query'.
    """
    from domain.pims.services.search_points_service import (
        search_pi_points as svc_search,
    )

    result = await svc_search(
        query=query,
        max_count=max_count,
        search_mode=search_mode,
    )
    return result["output"]


# ---------------------------------------------------------------------------
# Tool: generate_test_artifact_tool (referência / validação)
# ---------------------------------------------------------------------------
# A função é sempre definida (mantém importabilidade direta), mas o registro
# no FastMCP é condicional à feature flag ENABLE_TEST_ARTIFACT_TOOL.
# Default: false — tool omitida do catálogo em produção.
async def generate_test_artifact_tool(
    filename: str = "test_artifact.txt",
    content: str | None = None,
    mime_type: str = "text/plain",
    caption: str | None = None,
) -> str:
    """
    Gera um arquivo de teste, faz upload para a API do Agent Bot,
    e devolve envelope JSON com ChatAttachment.

    APENAS PARA VALIDAÇÃO — não usar em produção.
    Use esta tool para validar o fluxo de upload de artefatos.

    Args:
        filename: Nome do arquivo (default: test_artifact.txt).
        content: Conteúdo textual (opcional; padrão: timestamp).
        mime_type: MIME type do arquivo (default: text/plain).
        caption: Legenda para exibição no Google Chat (opcional).
    """
    from services.generate_test_artifact_service import generate_test_artifact

    return await generate_test_artifact(
        filename=filename,
        content=content,
        mime_type=mime_type,
        caption=caption,
    )

if settings.ENABLE_TEST_ARTIFACT_TOOL:
    mcp.tool(generate_test_artifact_tool)


# ---------------------------------------------------------------------------
# Tool: export_csv_to_drive_tool
# ---------------------------------------------------------------------------
async def export_csv_to_drive_tool(
    filename: str,
    columns: list[str],
    rows: list[list],
) -> dict:
    """
    Cria um arquivo CSV e envia para o Google Shared Drive.

    Use somente quando o usuário pedir explicitamente exportação CSV após
    obter dados. Limite: 500 linhas e 50 colunas.

    Args:
        filename: Nome do arquivo (sem caminho).
        columns: Lista de nomes de colunas.
        rows: Lista de linhas; cada linha deve ter o mesmo número de colunas.
    """
    from clients.google_drive_client import GoogleDriveClient, DriveCsvError
    from services.export_csv_to_drive_service import (
        export_csv_to_drive,
        DriveCsvValidationError,
        DriveCsvSerializationError,
    )

    if not settings.ENABLE_DRIVE_CSV_EXPORT_TOOL:
        return {
            "success": False,
            "answer": "Exportação CSV para Drive está desabilitada.",
            "error_code": "config_missing",
            "retryable": False,
        }

    try:
        client = GoogleDriveClient(
            credentials_path=settings.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE,
            folder_id=settings.GOOGLE_DRIVE_EXPORT_FOLDER_ID,
            timeout_seconds=settings.DRIVE_CSV_UPLOAD_TIMEOUT_SECONDS,
        )
        result = export_csv_to_drive(
            filename=filename,
            columns=columns,
            rows=rows,
            drive_client=client,
            max_rows=settings.DRIVE_CSV_MAX_ROWS,
            max_columns=settings.DRIVE_CSV_MAX_COLUMNS,
            max_cell_bytes=settings.DRIVE_CSV_MAX_CELL_BYTES,
            max_input_bytes=settings.DRIVE_CSV_MAX_INPUT_BYTES,
            max_file_bytes=settings.DRIVE_CSV_MAX_FILE_BYTES,
            max_filename_length=settings.DRIVE_CSV_MAX_FILENAME_LENGTH,
            formula_protection=settings.DRIVE_CSV_FORMULA_PROTECTION,
        )
        logger.info(
            "export_csv_to_drive_tool: success filename=%s",
            result.get("filename"),
        )
        return result
    except DriveCsvValidationError:
        return {
            "success": False,
            "answer": "Os dados enviados não são válidos para exportação CSV.",
            "error_code": "validation_error",
            "retryable": False,
        }
    except DriveCsvSerializationError:
        return {
            "success": False,
            "answer": "Erro ao serializar o arquivo CSV.",
            "error_code": "serialization_error",
            "retryable": False,
        }
    except DriveCsvError as e:
        logger.warning(
            "export_csv_to_drive_tool: error_code=%s retryable=%s",
            e.error_code,
            e.retryable,
        )
        return {
            "success": False,
            "answer": "Não foi possível criar o arquivo CSV no Google Drive.",
            "error_code": e.error_code,
            "retryable": e.retryable,
        }

if settings.ENABLE_DRIVE_CSV_EXPORT_TOOL:
    mcp.tool(export_csv_to_drive_tool)


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

    if settings.ENABLE_TEST_ARTIFACT_TOOL:
        logger.info("generate_test_artifact_tool: ENABLED (registrada no FastMCP)")
    else:
        logger.info(
            "generate_test_artifact_tool: DISABLED (omitida do registro — "
            "defina ENABLE_TEST_ARTIFACT_TOOL=true para habilitá-la)"
        )

    if settings.ENABLE_DRIVE_CSV_EXPORT_TOOL:
        logger.info("export_csv_to_drive_tool: ENABLED")
    else:
        logger.info(
            "export_csv_to_drive_tool: DISABLED — "
            "defina ENABLE_DRIVE_CSV_EXPORT_TOOL=true para habilitá-la"
        )

    asyncio.run(check_math_tool(settings.MATH_TOOL_BASE_URL))

    mcp.run(transport="http", host=settings.MCP_HOST, port=settings.MCP_PORT)
