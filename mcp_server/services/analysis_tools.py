from __future__ import annotations

import json
import logging
from typing import Literal

from fastmcp.exceptions import ToolError

from domain.analysis.formatters import InlineReportFormatter
from domain.analysis.models import AnalysisError, AnalysisRequest
from domain.analysis.services.pi_data_collector import PiDataCollector
from domain.analysis.services.tag_analysis_service import TagAnalysisService
from domain.shared.errors import DomainValidationError
from mcp_server.core.config import settings
from mcp_server.services.delivery._filename import build_filename
from mcp_server.services.delivery.contracts import (
    ArtifactMetadata,
    ErrorsSummaryItem,
    RequestSummary,
    WarningsItem,
)
from mcp_server.services.delivery.drive_publisher import DefaultDrivePublisher
from mcp_server.services.delivery.exceptions import ArtifactDeliveryError
from mcp_server.services.delivery.manifest_builder import build_artifact_manifest
from mcp_server.services.delivery.xlsx_report_builder import XlsxReportBuilder

logger = logging.getLogger("mcp_server.analysis_tools")


def _get_resolver_if_enabled():
    if settings.ENABLE_PI_POINT_RESOLVER_V2:
        from domain.pims.clients.pi_point_resolver import resolve_pi_point
        return resolve_pi_point
    return None


async def analyze_pi_tag_behavior(
    tag: str,
    start_time: str,
    end_time: str,
    zero_policy: Literal["valid", "suspicious", "invalid"] = "suspicious",
) -> str:
    request = AnalysisRequest(
        tag=tag,
        start_time=start_time,
        end_time=end_time,
        zero_policy=zero_policy,
    )

    try:
        TagAnalysisService().validate_request(request)
    except DomainValidationError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc

    collector = PiDataCollector(
        resolver=_get_resolver_if_enabled(),
    )
    data = await collector.fetch_one(tag, start_time, end_time)

    if isinstance(data, AnalysisError):
        raise ToolError(f"[{data.code}] {data.message}")

    service = TagAnalysisService()
    result = service.analyze_one(data, request)

    formatter = InlineReportFormatter()
    text = formatter.format(result)

    if len(text.encode("utf-8")) > settings.MCP_INLINE_MAX_BYTES:
        raise ToolError("[INLINE_PAYLOAD_TOO_LARGE] Resposta excede o limite inline.")

    return text


async def generate_pi_tags_analysis_report(
    tags: list[str],
    start_time: str,
    end_time: str,
    zero_policy: Literal["valid", "suspicious", "invalid"] = "invalid",
) -> str:
    request = AnalysisRequest(
        tags=tuple(tags),
        start_time=start_time,
        end_time=end_time,
        zero_policy=zero_policy,
    )

    try:
        TagAnalysisService().validate_request(request)
    except DomainValidationError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc

    collector = PiDataCollector(
        resolver=_get_resolver_if_enabled(),
    )
    collected = await collector.fetch_many(list(tags), start_time, end_time)

    service = TagAnalysisService()
    multi = service.analyze_many(collected, request)

    if multi.total_processed == 0:
        raise ToolError("[PI_SERIES_QUERY_ERROR] Nenhuma tag pôde ser processada.")

    from domain.analysis.services.xlsx_projection import XlsxAnalysisProjection

    projection = XlsxAnalysisProjection()
    sheets = projection.project(multi)

    builder = XlsxReportBuilder(
        temp_dir=settings.MCP_ARTIFACT_TEMP_DIR,
        max_rows=settings.MCP_ARTIFACT_MAX_ROWS,
        max_bytes=settings.MCP_ARTIFACT_MAX_BYTES,
        max_columns=settings.MCP_ARTIFACT_MAX_COLUMNS,
    )
    path = builder.build_xlsx(sheets)

    try:
        filename = build_filename(
            environment=settings.MCP_ARTIFACT_FILENAME_ENVIRONMENT,
            tool="pi_tags_analysis",
            extension="xlsx",
        )

        from mcp_server.clients.google_drive_client import GoogleDriveClient

        client = GoogleDriveClient(
            credentials_path=settings.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE or "",
            folder_id=settings.GOOGLE_DRIVE_EXPORT_FOLDER_ID or "",
            timeout_seconds=settings.MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS,
        )
        publisher = DefaultDrivePublisher(client)
        published = publisher.publish(
            file_bytes=path.read_bytes(),
            filename=filename,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            app_properties={
                "source": "pi-chat",
                "tool": "generate_pi_tags_analysis_report",
                "tags_processed": str(multi.total_processed),
                "environment": settings.MCP_ARTIFACT_FILENAME_ENVIRONMENT,
            },
        )

        status = "success" if not multi.errors else "partial_success"
        manifest_errors = [
            ErrorsSummaryItem(
                tag=e.tag,
                code=e.code,
                message=e.message[:300],
                retryable=e.retryable,
            )
            for e in multi.errors[:10]
        ]

        manifest = build_artifact_manifest(
            status=status,
            tool_name="generate_pi_tags_analysis_report",
            request_summary=RequestSummary(
                tool_name="generate_pi_tags_analysis_report",
                tags_requested=multi.total_requested,
                tags_processed=multi.total_processed,
                start_time=start_time,
                end_time=end_time,
                operation="analyze",
            ),
            artifact_metadata=ArtifactMetadata(
                format="xlsx",
                filename=published.name,
                mime_type=published.mime_type,
                row_count=sum(len(s.rows) for s in sheets),
                column_count=max((len(s.columns) for s in sheets), default=0),
                size_bytes=published.size_bytes,
                view_url=published.view_url,
            ),
            warnings=[],
            errors_summary=manifest_errors,
            max_manifest_bytes=settings.MCP_ARTIFACT_MANIFEST_MAX_BYTES,
        )

        return manifest.to_json()

    except ArtifactDeliveryError as exc:
        raise ToolError(f"[ARTIFACT_DELIVERY_ERROR] {exc}") from exc
    except Exception as exc:
        raise ToolError(f"[INTERNAL_TOOL_ERROR] {str(exc)[:200]}") from exc
    finally:
        path.unlink(missing_ok=True)
