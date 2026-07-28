"""Validate that the MCP schema for tag_statistics contains group_by enum."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

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


def _get_tool_parameters(tool_name: str = "tag_statistics"):
    import asyncio

    mcp = _import_mcp()
    tools = asyncio.run(mcp._tool_manager.get_tools())
    tool = tools.get(tool_name)
    assert tool is not None, f"Tool '{tool_name}' not found"
    return tool.parameters


def test_group_by_has_enum():
    params = _get_tool_parameters()
    props = params.get("properties", {})
    group_by = props.get("group_by")
    assert group_by is not None, "group_by property not found in schema"

    enum_values = _extract_enum(group_by)
    assert enum_values is not None, (
        f"No enum found in group_by schema: {group_by}"
    )
    assert "1m" in enum_values
    assert "1h" in enum_values
    assert "1d" in enum_values
    assert "1w" in enum_values
    assert "1mo" in enum_values


def test_group_by_enum_contains_1m():
    params = _get_tool_parameters()
    props = params.get("properties", {})
    group_by = props.get("group_by")
    assert group_by is not None

    enum_values = _extract_enum(group_by)
    assert enum_values is not None
    assert "1m" in enum_values


def test_group_by_default_is_1h():
    params = _get_tool_parameters()
    props = params.get("properties", {})
    group_by = props.get("group_by")
    assert group_by is not None
    assert group_by.get("default") == "1h", (
        f"group_by default should be '1h', got {group_by.get('default')}"
    )


def test_group_by_enum_does_not_contain_5m():
    params = _get_tool_parameters()
    props = params.get("properties", {})
    group_by = props.get("group_by")
    assert group_by is not None

    enum_values = _extract_enum(group_by)
    if enum_values is not None:
        assert "5m" not in enum_values


def _extract_enum(schema: dict) -> list[str] | None:
    any_of = schema.get("anyOf", [])
    for sub in any_of:
        enum = sub.get("enum")
        if enum is not None:
            return enum
    return schema.get("enum")
