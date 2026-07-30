"""Validate FastMCP.instructions constraints."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"


def _import_mcp():
    if str(_MCP_ROOT) not in sys.path:
        sys.path.insert(0, str(_MCP_ROOT))
    if str(_MCP_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(_MCP_ROOT.parent))
    if "mcp_server.server" not in sys.modules:
        importlib.import_module("mcp_server.server")
    from mcp_server.server import mcp

    return mcp


def test_instructions_max_8_lines():
    mcp = _import_mcp()
    instructions = mcp.instructions
    lines = [l for l in instructions.strip().splitlines() if l.strip()]
    assert len(lines) <= 8, f"Instructions has {len(lines)} lines (max 8)"


def test_instructions_contains_all_tools():
    mcp = _import_mcp()
    instructions = mcp.instructions
    tool_names = [
        "consultar_tag",
        "search_pi_points",
        "tag_attributes_tool",
        "tag_statistics_tool",
        "tag_calculus_tool",
        "status_pims_tool",
    ]
    for name in tool_names:
        assert name in instructions, f"Instructions missing reference to '{name}'"


def test_instructions_has_disambiguation():
    mcp = _import_mcp()
    instructions = mcp.instructions
    # Check for some disambiguation keyword
    has_desamb = "Desambiguação" in instructions or "dúvida" in instructions
    assert has_desamb, "Instructions missing disambiguation rule"


def test_instructions_mentions_schema_first():
    mcp = _import_mcp()
    instructions = mcp.instructions
    assert "inputSchema" in instructions or "Schema-first" in instructions, (
        "Instructions missing schema-first rule"
    )
