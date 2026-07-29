"""Validate that FastMCP envelope (content + structuredContent) does
NOT contain download_url."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.server import _mcp_safe_tool


@pytest.mark.asyncio
async def test_artifact_manifest_in_mcp_safe_tool_does_not_contain_download_url():
    """_mcp_safe_tool passes through the manifest dict without download_url."""
    manifest = {
        "schema_version": "1.0",
        "delivery": "drive_artifact",
        "tool_name": "tag_statistics",
        "artifact": {
            "row_count": 100,
            "view_url": "https://drive.google.com/view",
        },
    }

    async def _fake_inner():
        return manifest

    result = await _mcp_safe_tool(_fake_inner)
    serialized = json.dumps(result)
    assert "download_url" not in serialized
    assert "webContentLink" not in serialized
    assert result["artifact"]["view_url"] == "https://drive.google.com/view"


@pytest.mark.asyncio
async def test_inline_result_preserved():
    """Non-manifest results are passed through unchanged."""
    async def _inline():
        return {"status": "ok", "value": 42.0}

    result = await _mcp_safe_tool(_inline)
    assert result["value"] == 42.0
