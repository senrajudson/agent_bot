"""Contract tests: ArtifactManifest, ArtifactMetadata, PublishedArtifact
do NOT contain download_url."""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path
from unittest.mock import MagicMock

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.contracts import (
    ArtifactManifest,
    ArtifactMetadata,
    RequestSummary,
)
from mcp_server.services.delivery.drive_publisher import DefaultDrivePublisher, PublishedArtifact
from mcp_server.services.delivery.manifest_builder import build_artifact_manifest
from mcp_server.clients.google_drive_client import DriveUploadedFile


def test_artifact_metadata_has_no_download_url_field():
    field_names = {f.name for f in fields(ArtifactMetadata)}
    assert "download_url" not in field_names


def test_published_artifact_has_no_download_url_field():
    field_names = {f.name for f in fields(PublishedArtifact)}
    assert "download_url" not in field_names


def test_manifest_serialization_does_not_contain_download_url():
    meta = ArtifactMetadata(
        format="csv", filename="t.csv", mime_type="text/csv",
        row_count=10, column_count=3, size_bytes=500,
        view_url="https://drive.google.com/file/d/x/view",
    )
    manifest = ArtifactManifest(
        status="success", delivery="drive_artifact",
        tool_name="tag_statistics", artifact=meta,
    )
    serialized = json.dumps(manifest.to_dict())
    assert "download_url" not in serialized


def test_manifest_serialization_does_not_contain_webcontentlink():
    meta = ArtifactMetadata(
        format="csv", filename="t.csv", mime_type="text/csv",
        row_count=10, column_count=3, size_bytes=500,
        view_url="https://drive.google.com/file/d/x/view",
    )
    manifest = ArtifactManifest(
        status="success", delivery="drive_artifact",
        tool_name="tag_statistics", artifact=meta,
    )
    serialized = json.dumps(manifest.to_dict())
    assert "webContentLink" not in serialized


def test_default_drive_publisher_drops_webcontentlink():
    client = MagicMock()
    client.upload_csv.return_value = DriveUploadedFile(
        file_id="f1", name="t.csv", mime_type="text/csv",
        size=500, web_view_link="https://drive.google.com/view",
        web_content_link="https://drive.google.com/uc?id=f1",
        created_time="2026-07-28T12:00:00Z",
    )
    publisher = DefaultDrivePublisher(client)
    result = publisher.publish(file_bytes=b"a,b\n1,2", filename="t.csv", mime_type="text/csv")
    assert not hasattr(result, "download_url")
    assert not hasattr(result, "file_id")
    assert not hasattr(result, "created_time")


def test_manifest_stays_under_8kib():
    meta = ArtifactMetadata(
        format="csv", filename="t.csv", mime_type="text/csv",
        row_count=44640, column_count=5, size_bytes=1234567,
        view_url="https://drive.google.com/file/d/x/view",
    )
    manifest = build_artifact_manifest(
        status="success", tool_name="tag_statistics",
        request_summary=RequestSummary(tool_name="tag_statistics"),
        artifact_metadata=meta,
    )
    assert manifest.fits_in(8192)


def test_manifest_schema_version_remains_1_0():
    meta = ArtifactMetadata(
        format="csv", filename="t.csv", mime_type="text/csv",
        row_count=10, column_count=3, size_bytes=500,
        view_url="https://drive.google.com/file/d/x/view",
    )
    manifest = ArtifactManifest(
        status="success", delivery="drive_artifact",
        tool_name="test", artifact=meta,
    )
    assert manifest.schema_version == "1.0"


def test_view_url_is_required():
    with pytest.raises(TypeError):
        ArtifactMetadata(
            format="csv", filename="t.csv", mime_type="text/csv",
            row_count=10, column_count=3, size_bytes=500,
        )


def test_manifest_contains_view_url():
    meta = ArtifactMetadata(
        format="csv", filename="t.csv", mime_type="text/csv",
        row_count=10, column_count=3, size_bytes=500,
        view_url="https://drive.google.com/file/d/x/view",
    )
    manifest = ArtifactManifest(
        status="success", delivery="drive_artifact",
        tool_name="tag_statistics", artifact=meta,
    )
    d = manifest.to_dict()
    assert d["artifact"]["view_url"] == "https://drive.google.com/file/d/x/view"


def test_published_artifact_has_view_url():
    client = MagicMock()
    client.upload_file.return_value = DriveUploadedFile(
        file_id="f1", name="t.csv", mime_type="text/csv",
        size=500, web_view_link="https://drive.google.com/view",
        web_content_link=None, created_time="2026-07-28T12:00:00Z",
    )
    publisher = DefaultDrivePublisher(client)
    result = publisher.publish(file_bytes=b"a,b\n1,2", filename="t.csv", mime_type="text/csv")
    assert result.view_url == "https://drive.google.com/view"
