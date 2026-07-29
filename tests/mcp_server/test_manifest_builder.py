import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.manifest_builder import build_artifact_manifest
from mcp_server.services.delivery.contracts import (
    ArtifactMetadata,
    ErrorsSummaryItem,
    RequestSummary,
    WarningsItem,
)
from mcp_server.services.delivery.exceptions import ManifestSizeExceededError


def _make_summary():
    return RequestSummary(
        tool_name="tag_statistics",
        tags_requested=1,
        tags_processed=1,
        operation="mean",
        group_by="1m",
        start_time="2026-07-01T00:00:00Z",
        end_time="2026-07-31T23:59:59Z",
    )


def _make_artifact():
    return ArtifactMetadata(
        format="csv",
        filename="test.csv",
        mime_type="text/csv",
        row_count=44640,
        column_count=5,
        size_bytes=1234567,
        view_url="https://drive.google.com/view",
    )


class TestBuildArtifactManifest:
    def test_success(self):
        m = build_artifact_manifest(
            status="success",
            tool_name="tag_statistics",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
        )
        d = m.to_dict()
        assert d["status"] == "success"
        assert d["delivery"] == "drive_artifact"
        assert d["schema_version"] == "1.0"
        assert d["artifact"]["row_count"] == 44640
        assert "items_omitted" not in d

    def test_success_delivery_drive(self):
        m = build_artifact_manifest(
            status="success",
            tool_name="tag_statistics",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
        )
        assert m.delivery == "drive_artifact"

    def test_no_artifact_delivery_inline(self):
        m = build_artifact_manifest(
            status="success",
            tool_name="test",
            request_summary=_make_summary(),
            artifact_metadata=None,
        )
        assert m.delivery == "inline"

    def test_truncate_warnings(self):
        warnings = [WarningsItem(code=f"W{i}", message="x" * 50) for i in range(20)]
        m = build_artifact_manifest(
            status="partial_success",
            tool_name="test",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
            warnings=warnings,
        )
        assert len(m.warnings) <= 10
        assert m.items_omitted is not None and m.items_omitted >= 10

    def test_truncate_errors(self):
        errors = [ErrorsSummaryItem(tag=f"T{i}", code="ERR", message="abc") for i in range(15)]
        m = build_artifact_manifest(
            status="partial_success",
            tool_name="test",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
            errors_summary=errors,
        )
        assert len(m.errors_summary) <= 10
        assert m.items_omitted is not None and m.items_omitted >= 5

    def test_message_truncated_at_300(self):
        long_msg = "x" * 500
        errors = [ErrorsSummaryItem(tag="T1", code="ERR", message=long_msg)]
        m = build_artifact_manifest(
            status="partial_success",
            tool_name="test",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
            errors_summary=errors,
        )
        assert len(m.errors_summary[0].message) <= 303

    def test_manifest_respects_max_bytes(self):
        many_errors = [ErrorsSummaryItem(tag=f"T{i}", code="ERR", message="x" * 200) for i in range(50)]
        m = build_artifact_manifest(
            status="partial_success",
            tool_name="test",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
            errors_summary=many_errors,
            max_manifest_bytes=2048,
        )
        assert m.fits_in(2048)

    def test_items_omitted_absent_when_no_truncation(self):
        m = build_artifact_manifest(
            status="success",
            tool_name="test",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
        )
        assert m.items_omitted is None

    def test_critical_fields_preserved_after_truncation(self):
        errors = [ErrorsSummaryItem(tag=f"T{i}", code="ERR", message="x" * 100) for i in range(30)]
        m = build_artifact_manifest(
            status="partial_success",
            tool_name="tag_statistics",
            request_summary=_make_summary(),
            artifact_metadata=_make_artifact(),
            errors_summary=errors,
            max_manifest_bytes=1024,
        )
        assert m.status == "partial_success"
        assert m.delivery == "drive_artifact"
        assert m.artifact is not None
        assert m.artifact.view_url == "https://drive.google.com/view"
        assert m.artifact.row_count == 44640
