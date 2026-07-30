"""Regression test for importability of search_pi_points modules.

Validates that the service and server modules can be loaded
in a Python interpreter with the expected path setup.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

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


# ===================================================================
# T024 — FastMCP test for search_pi_points with AND
# ===================================================================
@pytest.mark.asyncio
async def test_search_pi_points_via_mcp_success() -> None:
    """FastMCP invocation: search_pi_points returns valid output."""
    mcp_root = Path(__file__).parent.parent.parent / "mcp_server"
    if str(mcp_root) not in sys.path:
        sys.path.insert(0, str(mcp_root))
    if str(mcp_root.parent) not in sys.path:
        sys.path.insert(0, str(mcp_root.parent))

    if "mcp_server.server" not in sys.modules:
        importlib.import_module("mcp_server.server")
    from mcp_server.server import search_pi_points

    with patch(
        "domain.pims.services.search_points_service.client_search",
        return_value={
            "Items": [
                {
                    "Name": "LFS_RB2_VELOPROC",
                    "Descriptor": "VELOCIDADE DO PROCESSO DO RB2",
                    "WebId": "W123",
                    "PointType": "Float32",
                    "EngineeringUnits": "m/min",
                }
            ]
        },
    ):
        result = await search_pi_points.run(
            arguments={"query": "velocidade rb2", "search_mode": "auto"},
        )
    assert result is not None
    assert result.content is not None
    assert len(result.content) > 0


@pytest.mark.asyncio
async def test_search_pi_points_via_mcp_no_match() -> None:
    """FastMCP: returns valid output even with no match."""
    mcp_root = Path(__file__).parent.parent.parent / "mcp_server"
    if str(mcp_root) not in sys.path:
        sys.path.insert(0, str(mcp_root))
    if str(mcp_root.parent) not in sys.path:
        sys.path.insert(0, str(mcp_root.parent))

    if "mcp_server.server" not in sys.modules:
        importlib.import_module("mcp_server.server")
    from mcp_server.server import search_pi_points

    with patch(
        "domain.pims.services.search_points_service.client_search",
        return_value={"Items": []},
    ):
        result = await search_pi_points.run(
            arguments={"query": "xxx yyy", "search_mode": "auto"},
        )
    assert result is not None
    assert result.content is not None
    assert len(result.content) > 0
