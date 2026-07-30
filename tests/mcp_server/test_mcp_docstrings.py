"""Validate MCP tool registration, docstrings, and signatures after docstring revert."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"

_TOOL_NAMES = [
    "consultar_tag",
    "search_pi_points",
    "tag_attributes_tool",
    "tag_statistics",
    "tag_calculus",
    "status_pims_tool",
]

_TOOL_NAMES_WITH_DRIVE = _TOOL_NAMES + ["export_csv_to_drive_tool"]


def _import_mcp_server():
    if str(_MCP_ROOT) not in sys.path:
        sys.path.insert(0, str(_MCP_ROOT))
    if str(_MCP_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(_MCP_ROOT.parent))
    if "mcp_server.server" not in sys.modules:
        importlib.import_module("mcp_server.server")
    from mcp_server.server import mcp

    return mcp


def _get_tool_fns():
    import mcp_server.server as server_mod

    result = {}
    for name in _TOOL_NAMES:
        wrapper = getattr(server_mod, name, None)
        if wrapper is None:
            continue
        fn = wrapper.fn if hasattr(wrapper, "fn") else wrapper
        result[name] = fn
    return result


@pytest.mark.asyncio
async def test_all_tools_registered():
    mcp = _import_mcp_server()
    import asyncio

    tools = await mcp.get_tools()
    # Minimum required tools are always present
    expected = set(_TOOL_NAMES)
    assert expected.issubset(set(tools.keys())), (
        f"Missing tools: {expected - set(tools.keys())}"
    )
    # Drive export tool may or may not be registered depending on flag
    if "export_csv_to_drive_tool" in tools:
        expected.add("export_csv_to_drive_tool")
    assert "create_csv_artifact_tool" not in tools, (
        "Removed tool 'create_csv_artifact_tool' should not be registered"
    )


def test_all_tools_have_docstring():
    tool_fns = _get_tool_fns()
    assert len(tool_fns) >= 6
    for name, fn in tool_fns.items():
        doc = fn.__doc__
        assert doc is not None, f"Tool '{name}' has no docstring"
        assert doc.strip(), f"Tool '{name}' has empty docstring"


def test_public_signatures_unchanged():
    """Verify that the 6 tool public signatures match expected baselines."""
    tool_fns = _get_tool_fns()

    baselines = {
        "consultar_tag": "(tags: list[str], pergunta_usuario: str | None = None) -> str",
        "search_pi_points": "(query: str, max_count: int = 5, search_mode: str = 'auto') -> str",
        "tag_attributes_tool": (
            "(tag: str, attribute_group: str = 'auto', "
            "attributes: list[str] | None = None) -> str"
        ),
        "tag_statistics": (
            "(tags: list[str], operation: str, start_time: str, "
            "end_time: str = '*', data_method: str = 'summary', "
            "interval: str | None = None, summary_type: str | None = None, "
            "summary_duration: str | None = None, "
            "calculation_basis: str | None = None, "
            "context_text: str | None = None, "
            "max_count: int = 200000, "
            "group_by: Optional[Literal['1m', '1h', '1d', '1w', '1mo']] = '1h', "
            "return_series: bool = False) -> str"
        ),
        "tag_calculus": (
            "(tags: list[str], operation: str, start_time: str, "
            "end_time: str = '*', data_method: str = 'interpolated', "
            "interval: str | None = None, summary_type: str | None = None, "
            "summary_duration: str | None = None, "
            "calculation_basis: str | None = None, "
            "time_unit: str = 'none', context_text: str | None = None, "
            "max_count: int = 200000) -> str"
        ),
        "status_pims_tool": "() -> str",
    }

    for name in _TOOL_NAMES:
        fn = tool_fns.get(name)
        assert fn is not None, f"Tool '{name}' not found"
        sig = str(inspect.signature(fn))
        expected = baselines[name]
        assert sig == expected, (
            f"Signature mismatch for '{name}':\n"
            f"  expected: {expected}\n"
            f"  got:      {sig}"
        )


def test_docstrings_dont_have_required_sections():
    """After the experimental revert, docstrings should NOT have
    the 6 required sections as structured headers."""
    tool_fns = _get_tool_fns()
    forbidden = [
        "Propósito:",
        "Quando usar:",
        "Quando NÃO usar:",
        "Anti-padrões:",
        "Saída:",
    ]
    for name, fn in tool_fns.items():
        doc = fn.__doc__ or ""
        for section in forbidden:
            assert section not in doc, (
                f"Tool '{name}' still has section '{section}'"
            )
