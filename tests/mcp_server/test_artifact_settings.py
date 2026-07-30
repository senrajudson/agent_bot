import sys
import os
from pathlib import Path

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from pydantic import ValidationError


def _make_valid_kwargs():
    return {
        "PI_WEB_API_BASE_URL": "http://fake",
        "ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY": False,
        "MCP_ARTIFACT_MAX_ROWS": 1000000,
        "MCP_ARTIFACT_MAX_BYTES": 104857600,
        "MCP_ARTIFACT_MAX_COLUMNS": 50,
        "MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS": 120,
        "MCP_ARTIFACT_TEMP_DIR": "/tmp",
        "MCP_ARTIFACT_MANIFEST_MAX_BYTES": 8192,
        "MCP_INLINE_MAX_BYTES": 65536,
    }


class TestArtifactSettings:
    def test_flag_off_does_not_require_drive(self):
        from core.config import Settings

        s = Settings(_env_file=None, **{**_make_valid_kwargs(), "ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY": False})
        assert s.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY is False

    def test_flag_on_requires_credentials(self):
        from core.config import Settings

        kwargs = _make_valid_kwargs()
        kwargs["ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY"] = True
        kwargs["GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE"] = None
        kwargs["GOOGLE_DRIVE_EXPORT_FOLDER_ID"] = None
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **kwargs)

    def test_flag_on_valid(self):
        from core.config import Settings

        kwargs = _make_valid_kwargs()
        kwargs["ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY"] = True
        kwargs["GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE"] = __file__
        kwargs["GOOGLE_DRIVE_EXPORT_FOLDER_ID"] = "folder1"
        s = Settings(_env_file=None, **kwargs)
        assert s.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY is True

    def test_inline_bytes_exceeds_artifact(self):
        from core.config import Settings

        kwargs = _make_valid_kwargs()
        kwargs["ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY"] = True
        kwargs["GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE"] = __file__
        kwargs["GOOGLE_DRIVE_EXPORT_FOLDER_ID"] = "folder1"
        kwargs["MCP_INLINE_MAX_BYTES"] = kwargs["MCP_ARTIFACT_MAX_BYTES"] + 1
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **kwargs)

    def test_artifact_max_rows_positive(self):
        from core.config import Settings

        kwargs = _make_valid_kwargs()
        kwargs["ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY"] = True
        kwargs["GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE"] = __file__
        kwargs["GOOGLE_DRIVE_EXPORT_FOLDER_ID"] = "folder1"
        kwargs["MCP_ARTIFACT_MAX_ROWS"] = -1
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **kwargs)
