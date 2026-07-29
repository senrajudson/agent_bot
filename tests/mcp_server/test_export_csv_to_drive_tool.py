"""Tests for MCP tool registration and execution."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))


CREDENTIAL_CLIENT = "mcp_server.clients.google_drive_client.service_account.Credentials"

# Convenient re-usable mock settings for enabled state
_ENABLED_SETTINGS = {
    "ENABLE_DRIVE_CSV_EXPORT_TOOL": True,
    "ENABLE_TEST_ARTIFACT_TOOL": False,
    "GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE": __file__,
    "GOOGLE_DRIVE_EXPORT_FOLDER_ID": "folder1",
    "DRIVE_CSV_MAX_ROWS": 500,
    "DRIVE_CSV_MAX_COLUMNS": 50,
    "DRIVE_CSV_MAX_CELL_BYTES": 32768,
    "DRIVE_CSV_MAX_INPUT_BYTES": 5242880,
    "DRIVE_CSV_MAX_FILE_BYTES": 10485760,
    "DRIVE_CSV_UPLOAD_TIMEOUT_SECONDS": 60.0,
    "DRIVE_CSV_MAX_FILENAME_LENGTH": 180,
    "DRIVE_CSV_FORMULA_PROTECTION": True,
}


# Flag false tests


@pytest.mark.asyncio
@patch("mcp_server.server.settings")
async def test_tool_not_registered_when_disabled(mock_settings):
    mock_settings.ENABLE_DRIVE_CSV_EXPORT_TOOL = False
    mock_settings.ENABLE_TEST_ARTIFACT_TOOL = False
    mock_settings.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY = False
    import importlib
    from domain.core.config import _reset_domain_settings
    try:
        _reset_domain_settings(test_only=True)
    except RuntimeError:
        pass
    import mcp_server.server as server_mod
    importlib.reload(server_mod)
    mcp = server_mod.mcp
    tools = await mcp.get_tools()
    assert "export_csv_to_drive_tool" not in tools


def test_tool_function_exists():
    import mcp_server.server as server_mod
    assert hasattr(server_mod, "export_csv_to_drive_tool")
    import inspect
    sig = str(inspect.signature(server_mod.export_csv_to_drive_tool))
    assert "filename" in sig
    assert "columns" in sig
    assert "rows" in sig


# Direct function tests (without FastMCP registry)


@pytest.mark.asyncio
@patch("mcp_server.server.settings")
async def test_disabled_returns_safe_error(mock_settings):
    mock_settings.ENABLE_DRIVE_CSV_EXPORT_TOOL = False
    import mcp_server.server as server_mod
    result = await server_mod.export_csv_to_drive_tool(
        filename="test.csv",
        columns=["A"],
        rows=[["1"]],
    )
    assert result["success"] is False
    assert result["error_code"] == "config_missing"
    assert result["retryable"] is False


@pytest.mark.asyncio
@patch("mcp_server.server.settings")
@patch(CREDENTIAL_CLIENT + ".from_service_account_file")
async def test_validation_error_returns_code(mock_cred, mock_settings):
    for k, v in _ENABLED_SETTINGS.items():
        setattr(mock_settings, k, v)
    mock_cred.return_value = MagicMock()
    import mcp_server.server as server_mod
    result = await server_mod.export_csv_to_drive_tool(
        filename="test.csv",
        columns=[],
        rows=[],
    )
    assert result["success"] is False
    assert result["error_code"] == "validation_error"
    assert result["retryable"] is False


@pytest.mark.asyncio
@patch("mcp_server.server.settings")
async def test_auth_error_returns_code(mock_settings):
    mock_settings.ENABLE_DRIVE_CSV_EXPORT_TOOL = True
    mock_settings.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE = "/nonexistent.json"
    mock_settings.GOOGLE_DRIVE_EXPORT_FOLDER_ID = "folder1"
    mock_settings.DRIVE_CSV_MAX_ROWS = 500
    mock_settings.DRIVE_CSV_MAX_COLUMNS = 50
    mock_settings.DRIVE_CSV_MAX_CELL_BYTES = 32768
    mock_settings.DRIVE_CSV_MAX_INPUT_BYTES = 5242880
    mock_settings.DRIVE_CSV_MAX_FILE_BYTES = 10485760
    mock_settings.DRIVE_CSV_UPLOAD_TIMEOUT_SECONDS = 60.0
    mock_settings.DRIVE_CSV_MAX_FILENAME_LENGTH = 180
    mock_settings.DRIVE_CSV_FORMULA_PROTECTION = True
    import mcp_server.server as server_mod
    result = await server_mod.export_csv_to_drive_tool(
        filename="test.csv",
        columns=["A"],
        rows=[["1"]],
    )
    assert result["success"] is False
    assert result["error_code"] == "credential_invalid"
    assert result["retryable"] is False


@pytest.mark.asyncio
@patch("mcp_server.server.settings")
@patch(CREDENTIAL_CLIENT + ".from_service_account_file")
async def test_success_returns_view_url(mock_cred, mock_settings):
    for k, v in _ENABLED_SETTINGS.items():
        setattr(mock_settings, k, v)
    mock_cred.return_value = MagicMock()

    from clients.google_drive_client import GoogleDriveClient

    from clients.google_drive_client import DriveUploadedFile

    with patch.object(GoogleDriveClient, "upload_csv") as mock_upload:
        mock_upload.return_value = DriveUploadedFile(
            file_id="abc123",
            name="test_file.csv",
            mime_type="text/csv",
            size=50,
            web_view_link="https://drive.google.com/file/d/abc123/view",
            web_content_link=None,
            created_time="2026-07-21T15:30:12Z",
        )
        import mcp_server.server as server_mod
        result = await server_mod.export_csv_to_drive_tool(
            filename="test_file.csv",
            columns=["A", "B"],
            rows=[["1", "2"]],
        )
    assert result["success"] is True
    assert "view" in result["view_url"]
    assert result["filename"] == "test_file.csv"
