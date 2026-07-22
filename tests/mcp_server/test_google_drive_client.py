"""Tests for GoogleDriveClient with full mocking."""

import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import httplib2
import pytest

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload


FAKE_CRED_PATH = __file__
FAKE_FOLDER_ID = "folder_abc123"
FAKE_TIMEOUT = 60.0
CLIENT_MODULE = "mcp_server.clients.google_drive_client"


def _mock_resp(status: int) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    return resp


@pytest.fixture
def mock_build():
    with patch(f"{CLIENT_MODULE}.build") as m:
        yield m


@pytest.fixture
def mock_credentials():
    with patch(f"{CLIENT_MODULE}.service_account.Credentials.from_service_account_file") as m:
        m.return_value = MagicMock()
        yield m


@pytest.fixture
def client(mock_credentials, mock_build):
    from mcp_server.clients.google_drive_client import GoogleDriveClient
    return GoogleDriveClient(
        credentials_path=FAKE_CRED_PATH,
        folder_id=FAKE_FOLDER_ID,
        timeout_seconds=FAKE_TIMEOUT,
    )


def test_scope_is_drive_file():
    from mcp_server.clients.google_drive_client import DRIVE_SCOPE
    assert DRIVE_SCOPE == "https://www.googleapis.com/auth/drive.file", (
        "Scope must be drive.file, not drive"
    )


def test_scope_not_drive():
    from mcp_server.clients.google_drive_client import DRIVE_SCOPE
    assert "auth/drive" in DRIVE_SCOPE
    assert not DRIVE_SCOPE.endswith("/drive"), "Must not use drive wide scope"


def test_credentials_called_with_path_and_scope(mock_credentials):
    from mcp_server.clients.google_drive_client import GoogleDriveClient, DRIVE_SCOPE, DriveCsvCredentialError
    mock_credentials.side_effect = ValueError("test")
    with pytest.raises(DriveCsvCredentialError):
        GoogleDriveClient(
            credentials_path=FAKE_CRED_PATH,
            folder_id=FAKE_FOLDER_ID,
            timeout_seconds=FAKE_TIMEOUT,
        )
    mock_credentials.assert_called_once_with(
        FAKE_CRED_PATH, scopes=[DRIVE_SCOPE]
    )


def test_credentials_nonexistent_file():
    from mcp_server.clients.google_drive_client import GoogleDriveClient, DriveCsvCredentialError
    with pytest.raises(DriveCsvCredentialError, match="não encontrada"):
        GoogleDriveClient(
            credentials_path="/nonexistent/path.json",
            folder_id=FAKE_FOLDER_ID,
            timeout_seconds=FAKE_TIMEOUT,
        )


def test_credentials_empty_folder():
    from mcp_server.clients.google_drive_client import GoogleDriveClient, DriveCsvCredentialError
    with pytest.raises(DriveCsvCredentialError, match="folder_id vazio"):
        GoogleDriveClient(
            credentials_path=FAKE_CRED_PATH,
            folder_id="",
            timeout_seconds=FAKE_TIMEOUT,
        )


def test_build_service_uses_timeout(client):
    from mcp_server.clients.google_drive_client import build as build_fn
    with patch(f"{CLIENT_MODULE}.build") as mock_build:
        service = client._build_service()
        mock_build.assert_called_once()
        _, kwargs = mock_build.call_args
        assert kwargs["cache_discovery"] is False


def test_build_service_authorized_http(mock_credentials, mock_build):
    from mcp_server.clients.google_drive_client import GoogleDriveClient, AuthorizedHttp
    mock_credentials.return_value = MagicMock()
    mcp_server_clients_google_drive_client_module = __import__(
        "mcp_server.clients.google_drive_client",
        fromlist=["google_drive_client"]
    )
    with patch(f"{CLIENT_MODULE}.AuthorizedHttp") as mock_auth_http:
        c = GoogleDriveClient(
            credentials_path=FAKE_CRED_PATH,
            folder_id=FAKE_FOLDER_ID,
            timeout_seconds=FAKE_TIMEOUT,
        )
        c._build_service()
        mock_auth_http.assert_called_once()
        args, _ = mock_auth_http.call_args
        assert args[0] is mock_credentials.return_value


def test_upload_csv_uses_media_io_base_upload(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file1",
        "name": "test.csv",
        "mimeType": "text/csv",
        "size": "100",
        "webViewLink": "https://drive.google.com/file/d/file1/view",
        "webContentLink": None,
        "createdTime": "2026-07-21T12:00:00Z",
    }
    result = client.upload_csv(
        filename="test_20260721_120000.csv",
        csv_bytes=b"col1;col2\r\n1;2\r\n",
        app_properties={"source": "pi-chat"},
    )
    _, kwargs = files_create_mock.call_args
    media = kwargs["media_body"]
    assert isinstance(media, MediaIoBaseUpload)
    assert media.mimetype() == "text/csv"
    assert media.resumable() is False


def test_upload_csv_parents_and_mime(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file2",
        "name": "test2.csv",
        "mimeType": "text/csv",
        "size": "50",
        "webViewLink": "https://drive.google.com/file/d/file2/view",
        "createdTime": "2026-07-21T12:00:00Z",
    }
    client.upload_csv(
        filename="test2.csv",
        csv_bytes=b"a;b\r\n1;2\r\n",
        app_properties={},
    )
    _, kwargs = files_create_mock.call_args
    body = kwargs["body"]
    assert body["parents"] == [FAKE_FOLDER_ID]
    assert body["mimeType"] == "text/csv"


def test_upload_csv_supports_all_drives(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file3",
        "name": "test3.csv",
        "mimeType": "text/csv",
        "size": "30",
        "webViewLink": "https://drive.google.com/file/d/file3/view",
        "createdTime": "2026-07-21T12:00:00Z",
    }
    client.upload_csv(
        filename="test3.csv",
        csv_bytes=b"x;y\r\n",
        app_properties={},
    )
    _, kwargs = files_create_mock.call_args
    assert kwargs["supportsAllDrives"] is True


def test_upload_csv_fields(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file4",
        "name": "test4.csv",
        "mimeType": "text/csv",
        "size": "10",
        "webViewLink": "https://drive.google.com/file/d/file4/view",
        "createdTime": "2026-07-21T12:00:00Z",
    }
    client.upload_csv(
        filename="test4.csv",
        csv_bytes=b"a\r\n",
        app_properties={},
    )
    _, kwargs = files_create_mock.call_args
    fields = kwargs["fields"]
    assert "webViewLink" in fields
    assert "webContentLink" in fields


def test_upload_csv_app_properties(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file5",
        "name": "test5.csv",
        "mimeType": "text/csv",
        "size": "10",
        "webViewLink": "https://drive.google.com/file/d/file5/view",
        "createdTime": "2026-07-21T12:00:00Z",
    }
    props = {"source": "pi-chat", "created_by_tool": "test"}
    client.upload_csv(
        filename="test5.csv",
        csv_bytes=b"a\r\n",
        app_properties=props,
    )
    _, kwargs = files_create_mock.call_args
    assert kwargs["body"]["appProperties"] == props


def test_upload_csv_metadata(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file_abc123def456",
        "name": "report.csv",
        "mimeType": "text/csv",
        "size": "200",
        "webViewLink": "https://drive.google.com/file/d/file_abc123def456/view",
        "webContentLink": "https://drive.google.com/uc?id=file_abc123def456",
        "createdTime": "2026-07-21T15:30:00Z",
    }
    result = client.upload_csv(
        filename="report.csv",
        csv_bytes=b"col\r\nval\r\n",
        app_properties={},
    )
    assert result.file_id == "file_abc123def456"
    assert result.name == "report.csv"
    assert result.mime_type == "text/csv"
    assert result.size == 200
    assert "view" in result.web_view_link
    assert result.web_content_link is not None
    assert "2026-07-21" in result.created_time


def test_upload_csv_web_content_link_optional(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file6",
        "name": "nodl.csv",
        "mimeType": "text/csv",
        "size": "5",
        "webViewLink": "https://drive.google.com/file/d/file6/view",
        "createdTime": "2026-07-21T12:00:00Z",
    }
    result = client.upload_csv(
        filename="nodl.csv",
        csv_bytes=b"a\r\n",
        app_properties={},
    )
    assert result.web_content_link is None
    assert result.web_view_link is not None


def test_upload_csv_missing_web_view_link_raises(client, mock_build):
    service_mock = mock_build.return_value
    files_create_mock = service_mock.files.return_value.create
    files_create_mock.return_value.execute.return_value = {
        "id": "file7",
        "name": "bad.csv",
        "mimeType": "text/csv",
        "size": "5",
        "createdTime": "2026-07-21T12:00:00Z",
    }
    from mcp_server.clients.google_drive_client import DriveCsvMetadataError
    with pytest.raises(DriveCsvMetadataError, match="webViewLink"):
        client.upload_csv(
            filename="bad.csv",
            csv_bytes=b"a\r\n",
            app_properties={},
        )


def test_upload_csv_empty_bytes_raises(client):
    from mcp_server.clients.google_drive_client import DriveCsvError
    with pytest.raises(DriveCsvError, match="vazio"):
        client.upload_csv(
            filename="empty.csv",
            csv_bytes=b"",
            app_properties={},
        )


def test_http_401_raises_auth_error(client, mock_build):
    service_mock = mock_build.return_value
    mock_execute = service_mock.files.return_value.create.return_value.execute
    mock_execute.side_effect = HttpError(_mock_resp(401), b"unauthorized")
    from mcp_server.clients.google_drive_client import DriveCsvAuthError
    with pytest.raises(DriveCsvAuthError):
        client.upload_csv(
            filename="test.csv",
            csv_bytes=b"a\r\n",
            app_properties={},
        )


def test_http_403_raises_auth_error(client, mock_build):
    service_mock = mock_build.return_value
    mock_execute = service_mock.files.return_value.create.return_value.execute
    mock_execute.side_effect = HttpError(_mock_resp(403), b"forbidden")
    from mcp_server.clients.google_drive_client import DriveCsvAuthError
    with pytest.raises(DriveCsvAuthError):
        client.upload_csv(
            filename="test.csv",
            csv_bytes=b"a\r\n",
            app_properties={},
        )


def test_http_404_raises_not_found(client, mock_build):
    service_mock = mock_build.return_value
    mock_execute = service_mock.files.return_value.create.return_value.execute
    mock_execute.side_effect = HttpError(_mock_resp(404), b"not found")
    from mcp_server.clients.google_drive_client import DriveCsvNotFoundError
    with pytest.raises(DriveCsvNotFoundError):
        client.upload_csv(
            filename="test.csv",
            csv_bytes=b"a\r\n",
            app_properties={},
        )


def test_http_429_raises_quota_error(client, mock_build):
    service_mock = mock_build.return_value
    mock_execute = service_mock.files.return_value.create.return_value.execute
    mock_execute.side_effect = HttpError(_mock_resp(429), b"quota")
    from mcp_server.clients.google_drive_client import DriveCsvQuotaError
    with pytest.raises(DriveCsvQuotaError) as exc_info:
        client.upload_csv(
            filename="test.csv",
            csv_bytes=b"a\r\n",
            app_properties={},
        )
    assert exc_info.value.retryable is True


def test_http_500_raises_upload_error(client, mock_build):
    service_mock = mock_build.return_value
    mock_execute = service_mock.files.return_value.create.return_value.execute
    mock_execute.side_effect = HttpError(_mock_resp(500), b"server error")
    from mcp_server.clients.google_drive_client import DriveCsvUploadError
    with pytest.raises(DriveCsvUploadError):
        client.upload_csv(
            filename="test.csv",
            csv_bytes=b"a\r\n",
            app_properties={},
        )


def test_http_503_raises_upload_error(client, mock_build):
    service_mock = mock_build.return_value
    mock_execute = service_mock.files.return_value.create.return_value.execute
    mock_execute.side_effect = HttpError(_mock_resp(503), b"unavailable")
    from mcp_server.clients.google_drive_client import DriveCsvUploadError
    with pytest.raises(DriveCsvUploadError):
        client.upload_csv(
            filename="test.csv",
            csv_bytes=b"a\r\n",
            app_properties={},
        )
