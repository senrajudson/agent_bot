"""Regression test for importability of search_pi_points modules.

Validates that the service and server modules can be loaded
in a Python interpreter with the expected path setup.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def test_service_module_importable() -> None:
    """Confirm domain.pims.services.search_points_service can be imported."""
    if "domain.pims.services.search_points_service" not in sys.modules:
        importlib.import_module("domain.pims.services.search_points_service")


async def _get_mcp_tool_names() -> set[str]:
    mcp_root = Path(__file__).parent.parent.parent / "mcp_server"
    if str(mcp_root) not in sys.path:
        sys.path.insert(0, str(mcp_root))
    if str(mcp_root.parent) not in sys.path:
        sys.path.insert(0, str(mcp_root.parent))

    if "mcp_server.server" not in sys.modules:
        importlib.import_module("mcp_server.server")
    from mcp_server.server import mcp

    tools = await mcp.get_tools()
    return set(tools.keys())


@pytest.mark.asyncio
async def test_server_module_importable() -> None:
    """Confirm mcp_server.server can be imported and search_pi_points is registered."""
    tool_names = await _get_mcp_tool_names()
    assert "search_pi_points" in tool_names
    assert "consultar_tag" in tool_names  # existing tools still present


def test_client_functions_importable() -> None:
    """Confirm search_pi_points and get_points_by_name_filter are accessible."""
    from domain.pims.clients.pi_web_api_client import (
        get_points_by_name_filter,
        search_pi_points,
    )

    assert callable(search_pi_points)
    assert callable(get_points_by_name_filter)
