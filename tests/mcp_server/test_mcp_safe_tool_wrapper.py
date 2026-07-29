"""
Testes do wrapper _mcp_safe_tool.

Valida que exceções conhecidas são propagadas ou convertidas,
e que exceções inesperadas viram INTERNAL_TOOL_ERROR sanitizado.
"""

import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from fastmcp.exceptions import ToolError

from mcp_server.server import _mcp_safe_tool


@pytest.mark.asyncio
async def test_successful_result():
    async def _ok():
        return {"result": "ok"}
    result = await _mcp_safe_tool(_ok)
    assert result == {"result": "ok"}


@pytest.mark.asyncio
async def test_tool_error_propagated():
    async def _raise_tool():
        raise ToolError("[TEST] original error")
    with pytest.raises(ToolError, match="original error"):
        await _mcp_safe_tool(_raise_tool)


@pytest.mark.asyncio
async def test_domain_validation_error_converted():
    from domain.shared.errors import DomainValidationError
    from domain.shared.errors import ValidationErrorCode

    async def _raise_dve():
        raise DomainValidationError(
            ValidationErrorCode.INVALID_GROUP_BY,
            "group_by inválido: 5m",
        )
    with pytest.raises(ToolError, match="INVALID_GROUP_BY"):
        await _mcp_safe_tool(_raise_dve)


@pytest.mark.asyncio
async def test_artifact_delivery_error_converted():
    from mcp_server.services.delivery.exceptions import (ArtifactDeliveryDisabledError,)

    async def _raise_ade():
        raise ArtifactDeliveryDisabledError(
            tool_name="tag_statistics",
            output_mode="series",
        )
    with pytest.raises(ToolError, match="ARTIFACT_DELIVERY_DISABLED"):
        await _mcp_safe_tool(_raise_ade)


@pytest.mark.asyncio
async def test_unbound_local_error_caught():
    async def _bad():
        x = x + 1  # UnboundLocalError
        return x
    with pytest.raises(ToolError, match="INTERNAL_TOOL_ERROR"):
        await _mcp_safe_tool(_bad)


@pytest.mark.asyncio
async def test_name_error_caught():
    async def _bad():
        return undefined_var  # name 'undefined_var' is not defined
    with pytest.raises(ToolError, match="INTERNAL_TOOL_ERROR"):
        await _mcp_safe_tool(_bad)


@pytest.mark.asyncio
async def test_key_error_caught():
    async def _bad():
        return {"a": 1}["missing"]
    with pytest.raises(ToolError, match="INTERNAL_TOOL_ERROR"):
        await _mcp_safe_tool(_bad)


@pytest.mark.asyncio
async def test_value_error_caught():
    async def _bad():
        raise ValueError("unexpected domain error")
    with pytest.raises(ToolError, match="INTERNAL_TOOL_ERROR"):
        await _mcp_safe_tool(_bad)


@pytest.mark.asyncio
async def test_runtime_error_caught():
    async def _bad():
        raise RuntimeError("unexpected runtime error")
    with pytest.raises(ToolError, match="INTERNAL_TOOL_ERROR"):
        await _mcp_safe_tool(_bad)


@pytest.mark.asyncio
async def test_no_data_preserved():
    async def _no_data():
        return {"status": "no_data", "tool_result": {}}
    result = await _mcp_safe_tool(_no_data)
    assert result["status"] == "no_data"


@pytest.mark.asyncio
async def test_insufficient_data_preserved():
    async def _insufficient():
        return {"status": "insufficient_data", "tool_result": {}}
    result = await _mcp_safe_tool(_insufficient)
    assert result["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_no_stack_trace_in_message():
    async def _bad():
        raise ValueError("internal detail")
    try:
        await _mcp_safe_tool(_bad)
    except ToolError as e:
        msg = str(e)
        assert "Traceback" not in msg
        assert "File" not in msg
        assert "internal detail" not in msg


@pytest.mark.asyncio
async def test_artifact_manifest_permitted():
    manifest = {
        "schema_version": "1.0",
        "delivery": "drive_artifact",
        "tool_name": "tag_statistics",
        "artifact": {
            "row_count": 100,
            "view_url": "https://drive.google.com/view",
        },
    }
    async def _manifest():
        return manifest
    result = await _mcp_safe_tool(_manifest)
    assert result["delivery"] == "drive_artifact"
