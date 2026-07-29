"""Tests for Drive CSV export configuration validation."""

import sys
from pathlib import Path

import pytest

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))


def _make_settings(**kwargs):
    from core.config import Settings
    defaults = dict(
        GRAFANA_LOKI_QUERY_RANGE_URL="http://fake",
        GRAFANA_BEARER_TOKEN="fake",
        ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY=False,
    )
    merged = {**defaults, **kwargs}
    return Settings(**merged)


def test_default_flag_false():
    """ENABLE_DRIVE_CSV_EXPORT_TOOL default is False."""
    s = _make_settings()
    assert s.ENABLE_DRIVE_CSV_EXPORT_TOOL is False


def test_false_allows_missing_credential():
    """When flag is false, credential and folder can be missing."""
    s = _make_settings(ENABLE_DRIVE_CSV_EXPORT_TOOL=False,
                       GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=None,
                       GOOGLE_DRIVE_EXPORT_FOLDER_ID=None)
    assert s.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE is None
    assert s.GOOGLE_DRIVE_EXPORT_FOLDER_ID is None


def test_true_raises_without_credential_path():
    """When flag is true, missing credential path raises ValueError."""
    with pytest.raises(ValueError, match="obrigatório"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=None,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
        )


def test_true_raises_with_empty_credential_path():
    """When flag is true, empty credential path raises ValueError."""
    with pytest.raises(ValueError, match="obrigatório"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE="",
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
        )


def test_true_raises_with_nonexistent_credential_file():
    """When flag is true, nonexistent credential file raises ValueError."""
    with pytest.raises(ValueError, match="não encontrada"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE="/nonexistent/path.json",
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
        )


def test_true_raises_without_folder():
    """When flag is true, missing folder ID raises ValueError."""
    with pytest.raises(ValueError, match="obrigatório"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID=None,
        )


def test_true_raises_with_empty_folder():
    """When flag is true, empty folder ID raises ValueError."""
    with pytest.raises(ValueError, match="obrigatório"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="",
        )


def test_true_raises_with_zero_rows():
    """Max rows must be positive."""
    with pytest.raises(ValueError, match="positivos"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
            DRIVE_CSV_MAX_ROWS=0,
        )


def test_true_raises_with_negative_columns():
    """Max columns must be positive."""
    with pytest.raises(ValueError, match="positivos"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
            DRIVE_CSV_MAX_COLUMNS=-1,
        )


def test_true_raises_input_exceeds_file():
    """Input bytes cannot exceed file bytes."""
    with pytest.raises(ValueError, match="exceder"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
            DRIVE_CSV_MAX_INPUT_BYTES=100,
            DRIVE_CSV_MAX_FILE_BYTES=50,
        )


def test_true_raises_invalid_timeout():
    """Timeout must be positive."""
    with pytest.raises(ValueError, match="positivo"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
            DRIVE_CSV_UPLOAD_TIMEOUT_SECONDS=0,
        )


def test_true_raises_invalid_filename_length():
    """Filename length must be positive."""
    with pytest.raises(ValueError, match="positivo"):
        _make_settings(
            ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
            GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
            GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
            DRIVE_CSV_MAX_FILENAME_LENGTH=0,
        )


def test_true_valid_config_passes():
    """Valid configuration passes without error."""
    s = _make_settings(
        ENABLE_DRIVE_CSV_EXPORT_TOOL=True,
        GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
        GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
    )
    assert s.ENABLE_DRIVE_CSV_EXPORT_TOOL is True
    assert s.GOOGLE_DRIVE_EXPORT_FOLDER_ID == "folder1"


def test_formula_protection_default_true():
    """Formula protection defaults to True."""
    s = _make_settings()
    assert s.DRIVE_CSV_FORMULA_PROTECTION is True


def test_formula_protection_can_be_false():
    """Formula protection can be set to False."""
    s = _make_settings(DRIVE_CSV_FORMULA_PROTECTION=False)
    assert s.DRIVE_CSV_FORMULA_PROTECTION is False
