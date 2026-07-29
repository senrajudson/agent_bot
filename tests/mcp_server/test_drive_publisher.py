import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.drive_publisher import DefaultDrivePublisher
from mcp_server.services.delivery.exceptions import DriveConfigError, ArtifactDeliveryError
from mcp_server.clients.google_drive_client import DriveCsvAuthError, DriveCsvQuotaError, DriveCsvError, DriveUploadedFile
from mcp_server.services.delivery.contracts import ArtifactManifest


def _make_mock_client():
    client = MagicMock()
    client.upload_csv.return_value = DriveUploadedFile(
        file_id="abc123",
        name="test.csv",
        mime_type="text/csv",
        size=5000,
        web_view_link="https://drive.google.com/view",
        web_content_link="https://drive.google.com/download",
        created_time="2026-07-28T12:00:00Z",
    )
    return client


class TestDefaultDrivePublisher:
    def test_publish_success(self):
        client = _make_mock_client()
        publisher = DefaultDrivePublisher(client)
        result = publisher.publish(
            file_bytes=b"a,b,c\n1,2,3",
            filename="test.csv",
            mime_type="text/csv",
        )
        assert result.file_id == "abc123"
        assert result.view_url == "https://drive.google.com/view"
        assert result.download_url == "https://drive.google.com/download"
        assert result.size_bytes == 5000

    def test_auth_error(self):
        client = MagicMock()
        client.upload_csv.side_effect = DriveCsvAuthError("auth error")
        publisher = DefaultDrivePublisher(client)
        with pytest.raises(DriveConfigError):
            publisher.publish(file_bytes=b"a", filename="test.csv", mime_type="text/csv")

    def test_quota_error(self):
        client = MagicMock()
        client.upload_csv.side_effect = DriveCsvQuotaError("quota error")
        publisher = DefaultDrivePublisher(client)
        with pytest.raises(ArtifactDeliveryError):
            publisher.publish(file_bytes=b"a", filename="test.csv", mime_type="text/csv")

    def test_upload_error(self):
        client = MagicMock()
        client.upload_csv.side_effect = DriveCsvError("upload error")
        publisher = DefaultDrivePublisher(client)
        with pytest.raises(ArtifactDeliveryError):
            publisher.publish(file_bytes=b"a", filename="test.csv", mime_type="text/csv")
