from __future__ import annotations

import json

from domain.analysis.models import (
    AnalysisError,
    AnalysisRequest,
    MultiTagAnalysisResult,
    QualityMetrics,
    TagAnalysisResult,
    TagMetadata,
)
from mcp_server.services.delivery.contracts import (
    ArtifactManifest,
    ArtifactMetadata,
    ErrorsSummaryItem,
    RequestSummary,
)


class TestArtifactManifest:
    def test_format_xlsx(self) -> None:
        manifest = ArtifactManifest(
            schema_version="1.0",
            status="success",
            delivery="drive_artifact",
            tool_name="generate_pi_tags_analysis_report",
            request_summary=RequestSummary(tool_name="test", tags_requested=1, tags_processed=1),
            artifact=ArtifactMetadata(
                format="xlsx",
                filename="test.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                row_count=10,
                column_count=5,
                size_bytes=1000,
                view_url="https://drive.google.com/file/d/xxx/view",
            ),
        )
        assert manifest.artifact is not None
        assert manifest.artifact.format == "xlsx"

    def test_mime_type(self) -> None:
        manifest = ArtifactManifest(
            schema_version="1.0",
            status="success",
            delivery="drive_artifact",
            tool_name="test",
            artifact=ArtifactMetadata(
                format="xlsx",
                filename="test.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                row_count=10,
                column_count=5,
                size_bytes=1000,
                view_url="https://drive.google.com/file/d/xxx/view",
            ),
        )
        assert "spreadsheetml" in manifest.artifact.mime_type

    def test_view_url_present(self) -> None:
        manifest = ArtifactManifest(
            schema_version="1.0",
            status="success",
            delivery="drive_artifact",
            tool_name="test",
            artifact=ArtifactMetadata(
                format="xlsx",
                filename="test.xlsx",
                mime_type="text/csv",
                row_count=10,
                column_count=5,
                size_bytes=1000,
                view_url="https://drive.google.com/file/d/xxx/view",
            ),
        )
        assert manifest.artifact.view_url.startswith("https://")

    def test_no_prohibited_fields(self) -> None:
        manifest = ArtifactManifest(
            schema_version="1.0",
            status="success",
            delivery="drive_artifact",
            tool_name="test",
            artifact=ArtifactMetadata(
                format="xlsx",
                filename="test.xlsx",
                mime_type="text/csv",
                row_count=10,
                column_count=5,
                size_bytes=1000,
                view_url="https://drive.google.com/file/d/xxx/view",
            ),
        )
        d = manifest.to_dict()
        assert "download_url" not in d.get("artifact", {})
        assert "file_id" not in d.get("artifact", {})
        assert "web_content_link" not in d.get("artifact", {})
        assert "created_time" not in d.get("artifact", {})

    def test_manifest_size_under_8192(self) -> None:
        manifest = ArtifactManifest(
            schema_version="1.0",
            status="success",
            delivery="drive_artifact",
            tool_name="test",
            artifact=ArtifactMetadata(
                format="xlsx",
                filename="test.xlsx",
                mime_type="text/csv",
                row_count=10,
                column_count=5,
                size_bytes=1000,
                view_url="https://drive.google.com/file/d/xxx/view",
            ),
            errors_summary=[
                ErrorsSummaryItem(tag="X", code="ERR", message="msg", retryable=False),
            ],
        )
        json_str = manifest.to_json()
        assert len(json_str.encode("utf-8")) <= 8192

    def test_partial_success_status(self) -> None:
        manifest = ArtifactManifest(
            schema_version="1.0",
            status="partial_success",
            delivery="drive_artifact",
            tool_name="test",
            artifact=ArtifactMetadata(
                format="xlsx",
                filename="test.xlsx",
                mime_type="text/csv",
                row_count=10,
                column_count=5,
                size_bytes=1000,
                view_url="https://drive.google.com/file/d/xxx/view",
            ),
            errors_summary=[
                ErrorsSummaryItem(tag="FAIL", code="PI_TIMEOUT", message="timeout", retryable=True),
            ],
        )
        assert manifest.status == "partial_success"
        assert len(manifest.errors_summary) == 1
