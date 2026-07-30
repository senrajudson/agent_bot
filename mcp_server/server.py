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

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mcp_server")

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from core.config import settings

from domain.core.config import configure_domain_settings
from domain.shared.errors import DomainValidationError
from domain.shared.schemas.math_tool import GroupBy
from domain.shared.time import resolve_pi_time_range
from mcp_server.services.delivery.output_delivery_policy import DefaultOutputDeliveryPolicy
from mcp_server.services.delivery.contracts import DeliveryMode
from mcp_server.services.delivery.exceptions import ArtifactDeliveryError

configure_domain_settings(settings.to_domain_integration_settings())

delivery_policy = DefaultOutputDeliveryPolicy(
    inline_max_rows=settings.MCP_INLINE_MAX_ROWS,
    inline_max_items=settings.MCP_INLINE_MAX_ITEMS,
    inline_max_bytes=settings.MCP_INLINE_MAX_BYTES,
    consultar_tag_artifact_max=20,
    consultar_tag_hard_cap=50,
)

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
        "→ tag_calculus_tool; disponibilidade da PI Web API (/dataservers) → status_pims_tool. "
        "Desambiguação: estatística simples → tag_statistics_tool; "
        "integral/derivada explícita → tag_calculus_tool. "
        "Valor atual → consultar_tag; atributos de configuração → tag_attributes_tool. "
        "Política: search_pi_points no máximo 2 vezes por turno; 2ª só com query diferente e se 1ª foi fraca; 3ª bloqueada. "
        "Schema-first: use apenas campos do inputSchema de cada tool. "
        "status_pims_tool é zero-argumento; chame com arguments={}."
    ),
)


# ---------------------------------------------------------------------------
# Barreira universal de tamanho (mcp_safe_tool)
# ---------------------------------------------------------------------------

_MANIFEST_CONTRACT_KEYS = {"schema_version", "delivery", "tool_name"}


def _is_artifact_manifest(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if not _MANIFEST_CONTRACT_KEYS.issubset(result.keys()):
        return False
    if result.get("delivery") != "drive_artifact":
        return False
    if not isinstance(result.get("artifact"), dict):
        return False
    if not result["artifact"].get("view_url"):
        return False
    return True


async def _mcp_safe_tool(tool_fn, *args, **kwargs):
    tool_name = getattr(tool_fn, "__name__", "unknown")
    try:
        result = await tool_fn(*args, **kwargs)
    except ToolError:
        raise
    except DomainValidationError as exc:
        code = getattr(exc, "code", None) or getattr(exc, "error_code", "VALIDATION_ERROR")
        raise ToolError(f"[{code}] {exc}") from exc
    except ArtifactDeliveryError as exc:
        public_code = getattr(exc, "public_code", "ARTIFACT_DELIVERY_ERROR")
        raise ToolError(f"[{public_code}] {exc}") from exc
    except Exception:
        logger.exception("Unexpected MCP tool failure", extra={"tool_name": tool_name})
        raise ToolError(
            f"[INTERNAL_TOOL_ERROR] Falha interna ao executar {tool_name}."
        )
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return result
        result = parsed

    serialized = json.dumps(result, ensure_ascii=False, default=str)
    size_bytes = len(serialized.encode("utf-8"))

    is_manifest = isinstance(result, dict) and _is_artifact_manifest(result)

    if is_manifest:
        if size_bytes > settings.MCP_ARTIFACT_MANIFEST_MAX_BYTES:
            raise ToolError(
                f"[MANIFEST_TOO_LARGE] "
                f"tool={tool_name} size_bytes={size_bytes} "
                f"max_bytes={settings.MCP_ARTIFACT_MANIFEST_MAX_BYTES}"
            )
        logger.info(
            "mcp_safe: tool=%s mode=DRIVE_ARTIFACT size=%d row_count=%s",
            tool_name, size_bytes,
            result.get("artifact", {}).get("row_count", "?"),
        )
        return result

    if size_bytes > settings.MCP_INLINE_MAX_BYTES:
        raise ToolError(
            f"[INLINE_PAYLOAD_TOO_LARGE] "
            f"tool={tool_name} size_bytes={size_bytes} "
            f"max_bytes={settings.MCP_INLINE_MAX_BYTES}"
        )

    logger.info(
        "mcp_safe: tool=%s mode=INLINE size=%d",
        tool_name, size_bytes,
    )
    return result


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
    async def _inner():
        decision = delivery_policy.decide(
            tool_name="consultar_tag",
            tags_count=len(tags),
        )
        if decision.mode == DeliveryMode.REJECT:
            raise ToolError(
                f"[TAG_COUNT_EXCEEDED] "
                f"Número de tags ({len(tags)}) excede o limite máximo permitido."
            )

        from domain.pims.services.consultar_tag_service import consultar_tags_pi

        result = await consultar_tags_pi(
            tags=tags,
            pergunta_usuario=pergunta_usuario or "",
            include_raw_response=False,
        )

        if decision.mode == DeliveryMode.DRIVE_ARTIFACT:
            from mcp_server.services.delivery.drive_publisher import DefaultDrivePublisher
            from mcp_server.services.delivery.report_builder import CsvReportBuilder
            from mcp_server.services.delivery.manifest_builder import build_artifact_manifest
            from mcp_server.services.delivery.contracts import ArtifactMetadata, RequestSummary
            from mcp_server.services.delivery._filename import build_filename
            from mcp_server.clients.google_drive_client import GoogleDriveClient

            resultados = result.get("tool_result", {}).get("resultados_pi", [])
            all_rows = []
            columns = ["Tag", "Descriptor", "Value", "Unit", "Timestamp", "DigitalState"]
            for r in resultados:
                all_rows.append([
                    r.get("tag", ""),
                    r.get("descriptor", ""),
                    r.get("valor_atual"),
                    r.get("eng_unit", ""),
                    r.get("timestamp", ""),
                    r.get("digital_state", ""),
                ])

            builder = CsvReportBuilder(
                temp_dir=settings.MCP_ARTIFACT_TEMP_DIR,
                encoding=settings.MCP_ARTIFACT_CSV_ENCODING,
                delimiter=settings.MCP_ARTIFACT_CSV_DELIMITER,
            )
            path = builder.build_csv(
                columns=columns,
                rows=all_rows,
                max_rows=settings.MCP_ARTIFACT_MAX_ROWS,
                max_bytes=settings.MCP_ARTIFACT_MAX_BYTES,
                max_cell_bytes=32768,
            )
            file_bytes = path.read_bytes()
            filename = build_filename(
                environment=settings.MCP_ARTIFACT_FILENAME_ENVIRONMENT,
                tool="consultar_tag",
                extension="csv",
            )
            client = GoogleDriveClient(
                credentials_path=settings.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE,
                folder_id=settings.GOOGLE_DRIVE_EXPORT_FOLDER_ID,
                timeout_seconds=settings.MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS,
            )
            publisher = DefaultDrivePublisher(client)
            uploaded = publisher.publish(
                file_bytes=file_bytes,
                filename=filename,
                mime_type="text/csv",
                app_properties={"source": "pi-chat", "tool": "consultar_tag"},
            )
            path.unlink(missing_ok=True)

            artifact_meta = ArtifactMetadata(
                format="csv",
                filename=uploaded.name,
                mime_type=uploaded.mime_type,
                row_count=len(all_rows),
                column_count=len(columns),
                size_bytes=uploaded.size_bytes,
                view_url=uploaded.view_url,
            )
            req_summary = RequestSummary(
                tool_name="consultar_tag",
                tags_requested=len(tags),
                tags_processed=len(resultados),
            )
            manifest = build_artifact_manifest(
                status="success",
                tool_name="consultar_tag",
                request_summary=req_summary,
                artifact_metadata=artifact_meta,
                max_manifest_bytes=settings.MCP_ARTIFACT_MANIFEST_MAX_BYTES,
            )
            return manifest.to_dict()

        return result["output"]
    return await _mcp_safe_tool(_inner)


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
    # Resolve defaults antes da closure para evitar UnboundLocalError
    if data_method == "summary":
        resolved_summary_type = summary_type or "Average"
        resolved_summary_duration = summary_duration or "1h"
        resolved_calculation_basis = calculation_basis or "TimeWeighted"
    else:
        resolved_summary_type = None
        resolved_summary_duration = None
        resolved_calculation_basis = None

    async def _inner():
        _output_mode = "series" if (group_by or return_series) else "scalar"

        if _output_mode == "series":
            norm_data_method = (data_method or "summary").strip().lower()
            if norm_data_method != "summary":
                raise ToolError(
                    f"[INVALID_DATA_METHOD_FOR_AGGREGATED_SERIES] "
                    f"Série estatística exige data_method='summary'. "
                    f"Recebido: '{data_method}'. "
                    f"Use generate_pi_tags_series_csv para séries interpoladas ou recorded."
                )
            _resolved_summary_duration = (
                summary_duration or group_by or "1h"
            )
            if summary_duration is not None and group_by is not None:
                norm_sd = summary_duration.strip().lower()
                norm_gb = group_by.strip().lower()
                if norm_sd != norm_gb:
                    raise ToolError(
                        f"[SUMMARY_DURATION_GROUP_BY_MISMATCH] "
                        f"summary_duration='{summary_duration}' difere de "
                        f"group_by='{group_by}'. Ambos devem ser iguais para "
                        f"série estatística."
                    )
        else:
            _resolved_summary_duration = summary_duration

        # Resolve tempos relativos da PI Web API uma vez por chamada
        _time_resolved = resolve_pi_time_range(start_time, end_time)
        _start_abs = _time_resolved.start_iso
        _end_abs = _time_resolved.end_iso
        logger.info(
            "tag_statistics: time_resolved input_kind=%s start_iso=%s end_iso=%s "
            "window_s=%s timezone=%s",
            _time_resolved.input_kind,
            _time_resolved.start_iso,
            _time_resolved.end_iso,
            _time_resolved.window_seconds,
            _time_resolved.timezone,
        )

        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service

        from core.config import settings as mcp_settings

        is_delivery_on = mcp_settings.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY

        # T013: fail-closed — série com flag false não retorna inline
        if _output_mode == "series" and not is_delivery_on:
            raise ToolError(
                "[ARTIFACT_DELIVERY_DISABLED] "
                "A entrega automática de artefatos está desabilitada. "
                "Séries temporais não podem ser retornadas inline."
            )

        artifact_publisher = None
        if is_delivery_on:
            from mcp_server.services.delivery.drive_publisher import DefaultDrivePublisher
            from mcp_server.services.delivery.report_builder import CsvReportBuilder
            from mcp_server.services.delivery.manifest_builder import build_artifact_manifest
            from mcp_server.services.delivery.contracts import (
                ArtifactMetadata,
                RequestSummary,
            )
            from mcp_server.services.delivery._filename import build_filename
            from mcp_server.clients.google_drive_client import GoogleDriveClient

            async def _artifact_publisher(artifact_data_list, summary):
                all_rows = []
                total_columns = ["Timestamp", "Tag", "Operation", "Value", "UnitsAbbreviation", "Quality"]
                for series_items, meta in artifact_data_list:
                    tag = meta.get("tag", "?")
                    operation_name = meta.get("operation", "?")
                    for item in series_items:
                        all_rows.append([
                            item.get("period_start", ""),
                            tag,
                            operation_name,
                            item.get("value"),
                            item.get("unit", ""),
                            item.get("quality", ""),
                        ])

                builder = CsvReportBuilder(
                    temp_dir=mcp_settings.MCP_ARTIFACT_TEMP_DIR,
                    encoding=mcp_settings.MCP_ARTIFACT_CSV_ENCODING,
                    delimiter=mcp_settings.MCP_ARTIFACT_CSV_DELIMITER,
                )
                path = builder.build_csv(
                    columns=total_columns,
                    rows=all_rows,
                    max_rows=mcp_settings.MCP_ARTIFACT_MAX_ROWS,
                    max_bytes=mcp_settings.MCP_ARTIFACT_MAX_BYTES,
                    max_cell_bytes=32768,
                )

                file_bytes = path.read_bytes()
                filename = build_filename(
                    environment=mcp_settings.MCP_ARTIFACT_FILENAME_ENVIRONMENT,
                    tool="tag_statistics",
                    extension="csv",
                )

                client = GoogleDriveClient(
                    credentials_path=mcp_settings.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE,
                    folder_id=mcp_settings.GOOGLE_DRIVE_EXPORT_FOLDER_ID,
                    timeout_seconds=mcp_settings.MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS,
                )
                publisher = DefaultDrivePublisher(client)
                uploaded = publisher.publish(
                    file_bytes=file_bytes,
                    filename=filename,
                    mime_type="text/csv",
                    app_properties={"source": "pi-chat", "tool": "tag_statistics"},
                )
                path.unlink(missing_ok=True)

                artifact_meta = ArtifactMetadata(
                    format="csv",
                    filename=uploaded.name,
                    mime_type=uploaded.mime_type,
                    row_count=len(all_rows),
                    column_count=len(total_columns),
                    size_bytes=uploaded.size_bytes,
                    view_url=uploaded.view_url,
                )

                req_summary = RequestSummary(
                    tool_name="tag_statistics",
                    tags_requested=len(tags),
                    tags_processed=len(artifact_data_list),
                    start_time=_start_abs,
                    end_time=_end_abs,
                    operation=operation,
                    group_by=str(group_by or ""),
                    output_mode="series",
                )

                manifest = build_artifact_manifest(
                    status="success",
                    tool_name="tag_statistics",
                    request_summary=req_summary,
                    artifact_metadata=artifact_meta,
                    max_manifest_bytes=mcp_settings.MCP_ARTIFACT_MANIFEST_MAX_BYTES,
                )
                return manifest.to_dict()
            artifact_publisher = _artifact_publisher

        _effective_summary_duration = (
            _resolved_summary_duration if _output_mode == "series"
            else resolved_summary_duration
        )

        result = await executar_estatistica_tags_service(
            tags=tags,
            operation=operation,
            start_time=_start_abs,
            end_time=_end_abs,
            interval=interval,
            max_count=max_count,
            data_method=data_method,
            summary_type=resolved_summary_type,
            summary_duration=_effective_summary_duration,
            calculation_basis=resolved_calculation_basis,
            group_by=group_by or "1h",
            return_series=return_series,
            drive_artifact_delivery=is_delivery_on,
            artifact_publisher=artifact_publisher,
        )

        if result.get("status") in ("invalid_argument", "internal_error"):
            error_code = result.get("error_code", "UNKNOWN")
            message = result.get("output", "Erro interno inesperado.")
            if result.get("status") == "internal_error":
                message = "Erro interno inesperado. Tente novamente."
            raise ToolError(f"[{error_code}] {message}")

        if result.get("status") in ("no_data", "insufficient_data"):
            return json.dumps(result.get("tool_result", {}), ensure_ascii=False)

        if result.get("delivery") == "drive_artifact":
            return result["tool_result"]

        return result["output"]

    return await _mcp_safe_tool(_inner)


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
    async def _inner():
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
    return await _mcp_safe_tool(_inner)


# ---------------------------------------------------------------------------
# Tool: status_pims_tool
# ---------------------------------------------------------------------------
@mcp.tool
async def status_pims_tool() -> str:
    """
    Verifica se a PI Web API do PIMS está acessível consultando o endpoint
    /dataservers.

    Retorna JSON compacto com available (bool), latency_ms (int),
    endpoint ("/dataservers"), error (string ou null) e
    latency_classification ("baixa"|"alta"|"indisponivel").

    Parâmetros: nenhum.
    Chamada: status_pims_tool({}).
    """
    async def _inner():
        from domain.pims_ops.services.status_pims_service import consultar_health_pi_web_api_service

        return await consultar_health_pi_web_api_service()
    return await _mcp_safe_tool(_inner)


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
    async def _inner():
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
    return await _mcp_safe_tool(_inner)


# ---------------------------------------------------------------------------
# Tool: generate_pi_tags_series_csv
# ---------------------------------------------------------------------------
@mcp.tool
async def generate_pi_tags_series_csv(
    tags: list[str],
    start_time: str,
    end_time: str = "*",
    data_method: str = "interpolated",
    interval: str | None = None,
) -> str:
    """
    Consulta valores temporais de tags PI sem agregação estatística, gera CSV
    completo e publica no Google Drive.

    Use quando o usuário pedir: valores minuto a minuto, série de valores,
    histórico de valores, valores interpolados, pontos registrados, valores
    brutos, exporte os valores em CSV, gere um CSV com os valores.

    NÃO use para: média, máximo, mínimo, soma, consumo, desvio padrão,
    mediana ou qualquer operação estatística. Para esses, use tag_statistics.

    Args:
        tags: Lista de tags (1 a 10).
        start_time: Início do período (PI token ou ISO 8601).
        end_time: Fim do período ('*' = agora). Janela [start, end).
        data_method: 'interpolated' (frequência definida) ou 'recorded' (eventos brutos).
        interval: Frequência para interpolated (ex: '1m', '5m', '1h', '1d').
                  Não usar para recorded. Default para interpolated: '1m'.
    """
    async def _inner():
        from domain.pims.services.generate_pi_tags_series_csv_service import (
            generate_pi_tags_series_csv_service,
        )
        from core.config import settings as mcp_settings

        if not mcp_settings.ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV:
            raise ToolError(
                "[DISABLED] generate_pi_tags_series_csv está desabilitada."
            )

        from mcp_server.services.delivery.drive_publisher import DefaultDrivePublisher
        from mcp_server.services.delivery.report_builder import CsvReportBuilder
        from mcp_server.services.delivery.manifest_builder import build_artifact_manifest
        from mcp_server.services.delivery.contracts import (
            ArtifactMetadata,
            RequestSummary,
            ErrorsSummaryItem,
            WarningsItem,
        )
        from mcp_server.services.delivery._filename import build_filename
        from mcp_server.clients.google_drive_client import GoogleDriveClient

        service_result = await generate_pi_tags_series_csv_service(
            tags=tags,
            start_time=start_time,
            end_time=end_time,
            data_method=data_method,
            interval=interval,
        )

        status = service_result.get("status", "no_data")

        if status == "no_data":
            tr = service_result.get("tool_result", {})
            return json.dumps({
                "schema_version": "1.0",
                "status": "no_data",
                "delivery": "inline",
                "tool_name": "generate_pi_tags_series_csv",
                "request_summary": {
                    "tags_requested": tr.get("tags_requested", len(tags)),
                    "tags_processed": 0,
                    "start_time": tr.get("start_time", start_time),
                    "end_time": tr.get("end_time", end_time),
                    "data_method": tr.get("data_method", data_method),
                    "interval": tr.get("interval", interval),
                },
                "message": "Nenhum dado encontrado para as tags e período informados.",
                "warnings": [],
                "errors_summary": [],
            }, ensure_ascii=False)

        if status == "all_failed":
            errors = service_result.get("errors_summary", [])
            raise ToolError(
                f"[PI_SERIES_QUERY_ERROR] Nenhuma tag pôde ser consultada. "
                f"Erros: {[e.get('tag', '?') + ': ' + e.get('error', '?') for e in errors]}"
            )

        rows = service_result.get("rows", [])
        tool_result = service_result.get("tool_result", {})
        column_headers = service_result.get("column_headers", [])
        errors_summary = service_result.get("errors_summary", [])

        builder = CsvReportBuilder(
            temp_dir=mcp_settings.MCP_SERIES_CSV_PUBLISH_TEMP_DIR,
            encoding=mcp_settings.MCP_ARTIFACT_CSV_ENCODING,
            delimiter=mcp_settings.MCP_ARTIFACT_CSV_DELIMITER,
        )

        csv_rows = []
        for r in rows:
            csv_rows.append([
                r.get("tag", ""),
                r.get("timestamp", ""),
                r.get("value") if r.get("value") is not None else "",
                r.get("eng_unit", ""),
                "true" if r.get("good") else "false",
                "true" if r.get("questionable") else "false",
                "true" if r.get("substituted") else "false",
                "true" if r.get("annotated") else "false",
                r.get("error", ""),
                r.get("value_type", ""),
                r.get("digital_state_code") if r.get("digital_state_code") is not None else "",
                r.get("digital_state_name") or "",
            ])

        path = builder.build_csv(
            columns=column_headers,
            rows=csv_rows,
            max_rows=mcp_settings.MCP_ARTIFACT_MAX_ROWS,
            max_bytes=mcp_settings.MCP_ARTIFACT_MAX_BYTES,
            max_cell_bytes=32768,
        )

        file_bytes = path.read_bytes()
        filename = build_filename(
            environment=mcp_settings.MCP_ARTIFACT_FILENAME_ENVIRONMENT,
            tool="pi_tags_series",
            extension="csv",
        )

        client = GoogleDriveClient(
            credentials_path=mcp_settings.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE,
            folder_id=mcp_settings.GOOGLE_DRIVE_EXPORT_FOLDER_ID,
            timeout_seconds=mcp_settings.MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS,
        )
        publisher = DefaultDrivePublisher(client)

        try:
            uploaded = publisher.publish(
                file_bytes=file_bytes,
                filename=filename,
                mime_type="text/csv",
                app_properties={"source": "pi-chat", "tool": "generate_pi_tags_series_csv"},
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            path.unlink(missing_ok=True)

        artifact_meta = ArtifactMetadata(
            format="csv",
            filename=uploaded.name,
            mime_type=uploaded.mime_type,
            row_count=len(csv_rows),
            column_count=len(column_headers),
            size_bytes=uploaded.size_bytes,
            view_url=uploaded.view_url,
        )

        req_summary = RequestSummary(
            tool_name="generate_pi_tags_series_csv",
            tags_requested=tool_result.get("tags_requested", len(tags)),
            tags_processed=tool_result.get("tags_processed", 0),
            start_time=tool_result.get("start_time", start_time),
            end_time=tool_result.get("end_time", end_time),
            data_method=tool_result.get("data_method", data_method),
        )

        manifest_errors = [
            ErrorsSummaryItem(tag=e.get("tag"), code="PI_SERIES_QUERY_ERROR", message=str(e.get("error", ""))[:300])
            for e in errors_summary
        ]

        manifest_errors_list = manifest_errors[:10]

        manifest = build_artifact_manifest(
            status=status,
            tool_name="generate_pi_tags_series_csv",
            request_summary=req_summary,
            artifact_metadata=artifact_meta,
            warnings=[],
            errors_summary=manifest_errors_list,
            max_manifest_bytes=mcp_settings.MCP_ARTIFACT_MANIFEST_MAX_BYTES,
        )

        return json.dumps(manifest.to_dict(), ensure_ascii=False)

    return await _mcp_safe_tool(_inner)


# ---------------------------------------------------------------------------
# Tool: search_pi_points
# ---------------------------------------------------------------------------
@mcp.tool
async def search_pi_points(
    query: str,
    max_count: int = 5,
    search_mode: str = "auto",
) -> str:
    """
    Busca tags/PI Points no PI Server por nome, descrição ou query textual.

    Use quando o usuário pedir para localizar, procurar, encontrar ou listar
    tags relacionadas a um termo, equipamento, área, variável ou descrição.

    Args:
        query: Termo de busca (parte do nome, descrição, equipamento, etc.).
        max_count: Máximo de resultados públicos (default 5).
        search_mode: 'auto', 'name', 'description', 'query'.
    """
    async def _inner():
        from domain.pims.services.search_points_service import (
            search_pi_points as svc_search,
        )

        result = await svc_search(
            query=query,
            max_count=max_count,
            search_mode=search_mode,
        )
        return result["output"]
    return await _mcp_safe_tool(_inner)


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
    async def _wrapped_ga(*args, **kwargs):
        async def _inner():
            return await generate_test_artifact_tool(*args, **kwargs)
        return await _mcp_safe_tool(_inner)
    # Preserve original docstring
    _wrapped_ga.__doc__ = generate_test_artifact_tool.__doc__
    # Register the wrapped version
    mcp.tool(_wrapped_ga, name="generate_test_artifact_tool")


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

    settings.log_effective_config()

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

    if settings.ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV:
        logger.info("generate_pi_tags_series_csv: ENABLED")
    else:
        logger.info(
            "generate_pi_tags_series_csv: DISABLED — "
            "defina ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=true para habilitá-la"
        )

    if settings.ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND:
        logger.info("search_pi_points: STRICT_AND ENABLED")
    else:
        logger.info(
            "search_pi_points: STRICT_AND DISABLED — "
            "defina ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND=true para habilitá-la"
        )

    asyncio.run(check_math_tool(settings.MATH_TOOL_BASE_URL))

    mcp.run(transport="http", host=settings.MCP_HOST, port=settings.MCP_PORT)
