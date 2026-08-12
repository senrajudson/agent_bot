import json
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.contracts import (
    ArtifactManifest,
    ArtifactMetadata,
    DeliveryDecision,
    DeliveryMode,
    ErrorsSummaryItem,
    RequestSummary,
    WarningsItem,
)


class TestArtifactManifest:
    def test_minimal_manifest(self):
        m = ArtifactManifest(
            status="success",
            delivery="drive_artifact",
            tool_name="tag_statistics",
        )
        d = m.to_dict()
        assert d["schema_version"] == "1.0"
        assert d["status"] == "success"
        assert d["delivery"] == "drive_artifact"
        assert d["tool_name"] == "tag_statistics"

    def test_to_json_compact(self):
        m = ArtifactManifest(status="success", delivery="drive_artifact", tool_name="test")
        js = m.to_json()
        assert isinstance(js, str)
        parsed = json.loads(js)
        assert parsed["status"] == "success"

    def test_fits_in_ok(self):
        m = ArtifactManifest(status="success", delivery="drive_artifact", tool_name="x")
        assert m.fits_in(8192) is True

    def test_fits_in_fail(self):
        big = ArtifactManifest(
            status="success",
            delivery="drive_artifact",
            tool_name="x" * 10000,
        )
        assert big.fits_in(512) is False

    def test_with_artifact_metadata(self):
        am = ArtifactMetadata(
            format="csv",
            filename="test.csv",
            mime_type="text/csv",
            row_count=100,
            column_count=5,
            size_bytes=5000,
            view_url="https://drive.google.com/view",
        )
        m = ArtifactManifest(
            status="success",
            delivery="drive_artifact",
            tool_name="tag_statistics",
            artifact=am,
        )
        d = m.to_dict()
        assert d["artifact"]["row_count"] == 100
        assert d["artifact"]["view_url"] == "https://drive.google.com/view"

    def test_items_omitted_absent_when_none(self):
        m = ArtifactManifest(status="success", delivery="drive_artifact", tool_name="x")
        d = m.to_dict()
        assert "items_omitted" not in d

    def test_items_omitted_present(self):
        m = ArtifactManifest(status="success", delivery="drive_artifact", tool_name="x", items_omitted=5)
        d = m.to_dict()
        assert d["items_omitted"] == 5

    def test_errors_summary_serialization(self):
        m = ArtifactManifest(
            status="partial_success",
            delivery="drive_artifact",
            tool_name="tag_statistics",
            errors_summary=[ErrorsSummaryItem(tag="TAG_A", code="PI_API_ERROR", message="Erro", retryable=False)],
        )
        d = m.to_dict()
        assert d["errors_summary"][0]["tag"] == "TAG_A"
        assert d["errors_summary"][0]["code"] == "PI_API_ERROR"

    def test_warning_without_tag_preserves_legacy_shape(self):
        m = ArtifactManifest(
            status="success",
            delivery="drive_artifact",
            tool_name="test",
            warnings=[WarningsItem(code="INFO", message="Mensagem")],
        )
        warning = m.to_dict()["warnings"][0]
        assert warning == {"code": "INFO", "message": "Mensagem"}

    def test_warning_with_tag_serializes_tag(self):
        m = ArtifactManifest(
            status="success",
            delivery="drive_artifact",
            tool_name="test",
            warnings=[WarningsItem(code="TAG_NO_DATA", message="Sem dados", tag="TAG_A")],
        )
        warning = m.to_dict()["warnings"][0]
        assert warning["tag"] == "TAG_A"


class TestDeliveryMode:
    def test_enum_values(self):
        assert DeliveryMode.INLINE.value == "inline"
        assert DeliveryMode.DRIVE_ARTIFACT.value == "drive_artifact"


class TestDeliveryDecision:
    def test_create(self):
        d = DeliveryDecision(mode=DeliveryMode.DRIVE_ARTIFACT, reason="series", suggested_format="csv")
        assert d.mode == DeliveryMode.DRIVE_ARTIFACT
        assert d.reason == "series"

    def test_default_format(self):
        d = DeliveryDecision(mode=DeliveryMode.INLINE, reason="default")
        assert d.suggested_format == "csv"


class TestRequestSummary:
    def test_create(self):
        r = RequestSummary(tool_name="tag_statistics", tags_requested=2, tags_processed=2)
        assert r.tool_name == "tag_statistics"


class TestErrorsSummaryItem:
    def test_create(self):
        e = ErrorsSummaryItem(tag="TAG_A", code="PI_API_ERROR", message="Erro", retryable=False)
        assert e.tag == "TAG_A"


class TestWarningsItem:
    def test_create(self):
        w = WarningsItem(code="NO_DATA", message="Tag sem dados")
        assert w.code == "NO_DATA"
