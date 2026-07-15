"""Validate that CHUNK 01 covers all 6 tools."""

import re
from pathlib import Path

_PROJECT = Path(__file__).parent.parent.parent
_GUIDE = _PROJECT / "PI_WEB_API_AGENT_GUIDE.md"


def test_chunk_01_contains_all_6_tools():
    text = _GUIDE.read_text(encoding="utf-8")

    # Extract CHUNK 01
    match = re.search(
        r"# CHUNK 01 - .+?\n(.*?)(?=\n# CHUNK 02 - |\Z)", text, re.DOTALL
    )
    assert match is not None, "CHUNK 01 not found in the document"
    chunk01 = match.group(0)

    tools = [
        "consultar_tag",
        "search_pi_points",
        "tag_attributes_tool",
        "tag_statistics_tool",
        "tag_calculus_tool",
        "status_pims_tool",
    ]

    for tool in tools:
        assert tool in chunk01, f"Tool '{tool}' not found in CHUNK 01"


def test_chunk_01_no_consultar_tag_tool_mismatch():
    """The MCP tool is named consultar_tag, not consultar_tag_tool."""
    text = _GUIDE.read_text(encoding="utf-8")
    match = re.search(
        r"# CHUNK 01 - .+?\n(.*?)(?=\n# CHUNK 02 - |\Z)", text, re.DOTALL
    )
    assert match is not None
    chunk01 = match.group(0)

    # consultar_tag can appear standalone or as part of markdown table
    # but consultar_tag_tool should NOT appear (it's the wrong name)
    assert "consultar_tag_tool" not in chunk01, (
        "CHUNK 01 uses 'consultar_tag_tool' instead of 'consultar_tag'"
    )


def test_chunk_01_has_routing_table():
    text = _GUIDE.read_text(encoding="utf-8")
    match = re.search(
        r"# CHUNK 01 - .+?\n(.*?)(?=\n# CHUNK 02 - |\Z)", text, re.DOTALL
    )
    assert match is not None
    chunk01 = match.group(0)
    assert "## Mapa de tools" in chunk01
