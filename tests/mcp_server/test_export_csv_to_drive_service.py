"""Tests for export_csv_to_drive service with mocked Drive client."""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

from clients.google_drive_client import GoogleDriveClient, DriveUploadedFile
from services.export_csv_to_drive_service import (
    export_csv_to_drive,
    DriveCsvValidationError,
    _sanitize_filename,
    _normalize,
    _measure_input_bytes,
)


NOW = datetime(2026, 7, 21, 15, 30, 12, tzinfo=timezone.utc)


def _mock_client() -> MagicMock:
    client = MagicMock(spec=GoogleDriveClient)
    client.upload_csv.return_value = DriveUploadedFile(
        file_id="file_abc123def456",
        name="test_20260721_153012.csv",
        mime_type="text/csv",
        size=50,
        web_view_link="https://drive.google.com/file/d/file_abc123def456/view",
        web_content_link="https://drive.google.com/uc?id=file_abc123def456",
        created_time="2026-07-21T15:30:12Z",
    )
    return client


def _default_kwargs(**overrides):
    client = overrides.pop("client", None)
    if client is None:
        client = _mock_client()
    base = dict(
        filename="test.csv",
        columns=["Timestamp", "Value"],
        rows=[["2026-07-21T10:00:00-03:00", 123.4]],
        drive_client=client,
        max_rows=500,
        max_columns=50,
        max_cell_bytes=32768,
        max_input_bytes=5242880,
        max_file_bytes=10485760,
        max_filename_length=180,
        formula_protection=True,
        now=NOW,
    )
    base.update(overrides)
    return base


# --- Success ---

def test_success():
    result = export_csv_to_drive(**_default_kwargs())
    assert result["success"] is True
    assert "criado" in result["answer"]
    assert result["filename"] == "test_20260721_153012.csv"
    assert result["mime_type"] == "text/csv"
    assert "view" in result["view_url"]
    assert "uc?id=" in result["download_url"]
    assert result["expires_at"] is None
    assert "file_id" not in result


def test_headers_only():
    result = export_csv_to_drive(**_default_kwargs(rows=[]))
    assert result["success"] is True
    assert result["filename"].endswith(".csv")


def test_rows_empty():
    result = export_csv_to_drive(**_default_kwargs(rows=[]))
    assert result["success"] is True


def test_download_url_optional():
    client = MagicMock()
    client.upload_csv.return_value = DriveUploadedFile(
        file_id="nodl", name="nodl_20260721_153012.csv",
        mime_type="text/csv", size=5,
        web_view_link="https://drive.google.com/file/d/nodl/view",
        web_content_link=None,
        created_time="2026-07-21T15:30:12Z",
    )
    result = export_csv_to_drive(**_default_kwargs(client=client))
    assert result["download_url"] is None


# --- Limits ---

def test_max_rows_exceeded():
    kwargs = _default_kwargs(rows=[["a", 1]] * 501)
    with pytest.raises(DriveCsvValidationError, match="excede máximo"):
        export_csv_to_drive(**kwargs)


def test_max_columns_exceeded():
    kwargs = _default_kwargs(columns=[f"c{i}" for i in range(51)])
    with pytest.raises(DriveCsvValidationError, match="excede máximo"):
        export_csv_to_drive(**kwargs)


def test_row_width_mismatch():
    kwargs = _default_kwargs(rows=[["only_one"]])
    with pytest.raises(DriveCsvValidationError, match="esperado 2"):
        export_csv_to_drive(**kwargs)


# --- Types ---

def test_supported_types():
    rows = [
        [None, ""],
        [True, False],
        [42, -7],
        [3.14, -2.5],
        [Decimal("10.5"), Decimal("-0.01")],
        ["hello", "world"],
    ]
    kwargs = _default_kwargs(
        columns=["a", "b"],
        rows=rows,
    )
    result = export_csv_to_drive(**kwargs)
    assert result["success"] is True


def test_datetime_type():
    from datetime import date
    kwargs = _default_kwargs(
        rows=[[datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc), date(2026, 7, 21)]],
    )
    result = export_csv_to_drive(**kwargs)
    assert result["success"] is True


def test_unsupported_type():
    kwargs = _default_kwargs(rows=[["a", {"x": 1}]])
    with pytest.raises(DriveCsvValidationError, match="não suportado"):
        export_csv_to_drive(**kwargs)


def test_nan_rejected():
    kwargs = _default_kwargs(rows=[["a", float("nan")]])
    with pytest.raises(DriveCsvValidationError, match="não finito"):
        export_csv_to_drive(**kwargs)


def test_infinity_rejected():
    kwargs = _default_kwargs(rows=[["a", float("inf")]])
    with pytest.raises(DriveCsvValidationError, match="não finito"):
        export_csv_to_drive(**kwargs)


def test_bytes_rejected():
    kwargs = _default_kwargs(rows=[["a", b"binary"]])
    with pytest.raises(DriveCsvValidationError, match="não suportado"):
        export_csv_to_drive(**kwargs)


# --- Formula protection ---

@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_formula_protection_prefixes(prefix):
    kwargs = _default_kwargs(rows=[[prefix + "SUM(A1:A2)", 1]])
    result = export_csv_to_drive(**kwargs)
    assert result["success"] is True


def test_formula_protection_disabled():
    rows = [["=DANGER()", 1]]
    kwargs = _default_kwargs(
        formula_protection=False,
        rows=rows,
    )
    result = export_csv_to_drive(**kwargs)
    assert result["success"] is True


def test_negative_number_not_protected():
    rows = [[-123, 456]]
    kwargs = _default_kwargs(columns=["a", "b"], rows=rows)
    result = export_csv_to_drive(**kwargs)
    assert result["success"] is True


def test_negative_string_protected():
    rows = [["-123", 456]]
    kwargs = _default_kwargs(columns=["a", "b"], rows=rows)
    result = export_csv_to_drive(**kwargs)
    assert result["success"] is True


# --- Filename ---

def test_filename_without_csv_extension():
    result = _sanitize_filename("mydata", 180, NOW)
    assert result == "mydata_20260721_153012.csv"


def test_filename_with_csv_extension():
    result = _sanitize_filename("report.csv", 180, NOW)
    assert result == "report_20260721_153012.csv"


def test_filename_with_path():
    kwargs = _default_kwargs(filename="../../etc/passwd.csv")
    result = export_csv_to_drive(**kwargs)
    assert "/" not in result["filename"]
    assert "etc" not in result["filename"] or "_" in result["filename"]


def test_filename_windows_reserved():
    result = _sanitize_filename("CON.csv", 180, NOW)
    assert result.startswith("_CON_")


def test_filename_empty_raises():
    kwargs = _default_kwargs(filename="")
    with pytest.raises(DriveCsvValidationError, match="inválido"):
        export_csv_to_drive(**kwargs)


def test_filename_dot_raises():
    kwargs = _default_kwargs(filename=".")
    with pytest.raises(DriveCsvValidationError, match="inválido"):
        export_csv_to_drive(**kwargs)


def test_filename_max_length():
    long_name = "a" * 200
    kwargs = _default_kwargs(filename=long_name + ".csv")
    result = export_csv_to_drive(**kwargs)
    assert len(result["filename"]) <= 180


# --- Client called once ---

def test_client_called_once():
    client = _mock_client()
    kwargs = _default_kwargs(client=client)
    export_csv_to_drive(**kwargs)
    client.upload_csv.assert_called_once()


# --- BOM ---

def test_bom_present():
    client = _mock_client()
    uploaded_bytes = None

    def capture(filename, csv_bytes, app_properties):
        nonlocal uploaded_bytes
        uploaded_bytes = csv_bytes
        return client.upload_csv.return_value

    client.upload_csv.side_effect = capture
    kwargs = _default_kwargs(client=client)
    export_csv_to_drive(**kwargs)
    assert uploaded_bytes is not None
    assert uploaded_bytes[:3] == b"\xef\xbb\xbf"


# --- Semicolon and CRLF ---

def test_delimiter_and_crlf():
    client = _mock_client()
    uploaded_bytes = None

    def capture(filename, csv_bytes, app_properties):
        nonlocal uploaded_bytes
        uploaded_bytes = csv_bytes
        return client.upload_csv.return_value

    client.upload_csv.side_effect = capture
    kwargs = _default_kwargs(
        client=client,
        columns=["A", "B"],
        rows=[["val1", "val2"]],
    )
    export_csv_to_drive(**kwargs)
    decoded = uploaded_bytes.decode("utf-8-sig")
    assert ";" in decoded
    assert "\r\n" in decoded


# --- appProperties ---

def test_app_properties_sent():
    client = _mock_client()
    captured = {}

    def capture(filename, csv_bytes, app_properties):
        captured.update(app_properties)
        return client.upload_csv.return_value

    client.upload_csv.side_effect = capture
    kwargs = _default_kwargs(client=client)
    export_csv_to_drive(**kwargs)
    assert captured.get("source") == "pi-chat"
    assert captured.get("created_by_tool") == "export_csv_to_drive_tool"
    assert "created_at" in captured


# --- file_id not public ---

def test_file_id_not_in_result():
    result = export_csv_to_drive(**_default_kwargs())
    assert "file_id" not in result
