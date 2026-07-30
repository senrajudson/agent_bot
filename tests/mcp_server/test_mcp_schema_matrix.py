"""Validate that all registered MCP tools expose a correct inputSchema.

The schema exposed by tools/list is the normative source of truth for tool
arguments. System prompt, docstrings and instructions are complementary and
must be tested against the actual schema.

This test derives the matrix in runtime so it never goes stale.
"""

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


_CONTEXT_PARAMS = {"context_text", "pergunta_usuario"}


@pytest.mark.asyncio
async def test_tool_schema_matrix():
    """Validate that every registered tool has a valid inputSchema,
    and zero-argument tools do not accept context_text or pergunta_usuario."""
    mcp = _import_mcp()
    tools = await mcp.get_tools()

    assert isinstance(tools, dict), "get_tools() must return a dict"
    assert len(tools) >= 6, f"Expected at least 6 tools, got {len(tools)}"

    zero_arg_tools = []
    table_rows = []

    for name in sorted(tools.keys()):
        tool = tools[name]
        # FastMCP tools expose inputSchema via to_mcp_tool()
        mcp_tool = tool.to_mcp_tool()
        schema = mcp_tool.inputSchema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        accepts_context = "context_text" in properties
        accepts_pergunta = "pergunta_usuario" in properties

        table_rows.append({
            "name": name,
            "properties": list(properties.keys()),
            "required": required,
            "accepts_context_text": accepts_context,
            "accepts_pergunta_usuario": accepts_pergunta,
        })

        if not properties:
            zero_arg_tools.append(name)

    # Every zero-argument tool must NOT accept context_text or pergunta_usuario
    for row in table_rows:
        if not row["properties"]:
            assert not row["accepts_context_text"], (
                f"Tool {row['name']} has zero properties but accepts context_text"
            )
            assert not row["accepts_pergunta_usuario"], (
                f"Tool {row['name']} has zero properties but accepts pergunta_usuario"
            )

    # At least status_pims_tool must be zero-argument
    assert "status_pims_tool" in zero_arg_tools, (
        "status_pims_tool must be a zero-argument tool"
    )

    # Log the matrix for debugging
    _log_matrix(table_rows)


def _log_matrix(rows: list[dict]) -> None:
    """Log the tool schema matrix for inspection in CI."""
    lines = ["\nTool Schema Matrix:", f"{'Tool':<40} {'Props':<45} {'Required':<30} {'ctx':<5} {'perg':<5}"]
    lines.append("-" * 125)
    for r in rows:
        props = ", ".join(r["properties"]) if r["properties"] else "(none)"
        req = ", ".join(r["required"]) if r["required"] else "(none)"
        lines.append(
            f"{r['name']:<40} {props:<45} {req:<30} "
            f"{'Y' if r['accepts_context_text'] else 'N':<5} "
            f"{'Y' if r['accepts_pergunta_usuario'] else 'N':<5}"
        )
    print("\n".join(lines))
