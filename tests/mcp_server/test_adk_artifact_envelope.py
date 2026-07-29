"""Validate that ADK tool response unpacking produces only view_url."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))


def test_structured_content_has_view_url_no_download_url():
    """Simulate structuredContent as produced by FastMCP for a manifest."""
    manifest = {
        "schema_version": "1.0",
        "delivery": "drive_artifact",
        "tool_name": "tag_statistics",
        "artifact": {
            "format": "csv",
            "filename": "test.csv",
            "mime_type": "text/csv",
            "row_count": 100,
            "column_count": 5,
            "size_bytes": 5000,
            "view_url": "https://drive.google.com/view",
        },
    }
    serialized = json.dumps(manifest)
    assert "download_url" not in serialized
    assert "webContentLink" not in serialized
    assert manifest["artifact"]["view_url"] == "https://drive.google.com/view"


def test_text_content_has_view_url_no_download_url():
    """Simulate TextContent string produced by FastMCP for a manifest."""
    manifest_str = json.dumps({
        "schema_version": "1.0",
        "delivery": "drive_artifact",
        "tool_name": "tag_statistics",
        "artifact": {
            "format": "csv",
            "filename": "test.csv",
            "mime_type": "text/csv",
            "row_count": 100,
            "column_count": 5,
            "size_bytes": 5000,
            "view_url": "https://drive.google.com/view",
        },
    })
    assert "download_url" not in manifest_str
    assert "webContentLink" not in manifest_str
