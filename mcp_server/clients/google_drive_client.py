from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import httplib2
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger("mcp_server.google_drive_client")

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_API_NAME = "drive"
DRIVE_API_VERSION = "v3"

_CREATE_FIELDS = (
    "id,name,mimeType,size,webViewLink,webContentLink,createdTime"
)


class DriveCsvError(Exception):
    error_code: str = "drive_upload_error"
    retryable: bool = False


class DriveCsvCredentialError(DriveCsvError):
    error_code = "credential_invalid"
    retryable = False


class DriveCsvAuthError(DriveCsvError):
    error_code = "drive_auth_error"
    retryable = False


class DriveCsvNotFoundError(DriveCsvError):
    error_code = "drive_not_found"
    retryable = False


class DriveCsvQuotaError(DriveCsvError):
    error_code = "drive_quota_error"
    retryable = True


class DriveCsvTimeoutError(DriveCsvError):
    error_code = "drive_timeout"
    retryable = True


class DriveCsvUploadError(DriveCsvError):
    error_code = "drive_upload_error"


class DriveCsvMetadataError(DriveCsvError):
    error_code = "drive_metadata_error"
    retryable = False


@dataclass(frozen=True)
class DriveUploadedFile:
    file_id: str
    name: str
    mime_type: str
    size: int
    web_view_link: str
    web_content_link: str | None
    created_time: str


def _mask_id(full_id: str) -> str:
    if len(full_id) <= 8:
        return full_id
    return full_id[:8] + "..."


def _map_http_error(e: HttpError) -> DriveCsvError:
    status = getattr(e.resp, "status", 0)
    if status in (401, 403):
        return DriveCsvAuthError(f"status={status}")
    if status == 404:
        return DriveCsvNotFoundError(f"status={status}")
    if status == 429:
        return DriveCsvQuotaError(f"status={status}")
    if 500 <= status < 600:
        return DriveCsvUploadError(f"status={status}")
    return DriveCsvUploadError(f"status={status}")


class GoogleDriveClient:
    def __init__(
        self,
        *,
        credentials_path: str,
        folder_id: str,
        timeout_seconds: float,
    ) -> None:
        if not Path(credentials_path).is_file():
            raise DriveCsvCredentialError(
                f"Credencial não encontrada: {credentials_path}"
            )
        if not folder_id:
            raise DriveCsvCredentialError("folder_id vazio.")
        try:
            self._credentials = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=[DRIVE_SCOPE]
            )
        except (GoogleAuthError, ValueError) as e:
            raise DriveCsvCredentialError(str(e)) from e
        self._folder_id = folder_id
        self._timeout = timeout_seconds

    def _build_service(self):
        http = httplib2.Http(timeout=self._timeout)
        authorized_http = AuthorizedHttp(self._credentials, http=http)
        return build(
            DRIVE_API_NAME,
            DRIVE_API_VERSION,
            http=authorized_http,
            cache_discovery=False,
        )

    def upload_file(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        mime_type: str,
        app_properties: dict[str, str],
    ) -> DriveUploadedFile:
        if not file_bytes:
            raise DriveCsvError("file_bytes vazio.")
        service = self._build_service()
        media = MediaIoBaseUpload(
            BytesIO(file_bytes), mimetype=mime_type, resumable=False
        )
        body = {
            "name": filename,
            "parents": [self._folder_id],
            "mimeType": mime_type,
            "appProperties": dict(app_properties),
        }
        try:
            response = (
                service.files()
                .create(
                    body=body,
                    media_body=media,
                    supportsAllDrives=True,
                    fields=_CREATE_FIELDS,
                )
                .execute()
            )
        except HttpError as e:
            raise _map_http_error(e) from e

        web_view = response.get("webViewLink")
        if not web_view:
            raise DriveCsvMetadataError(
                "Resposta da API sem webViewLink."
            )

        uploaded = DriveUploadedFile(
            file_id=response.get("id", ""),
            name=response.get("name", filename),
            mime_type=response.get("mimeType", mime_type),
            size=int(response.get("size") or 0),
            web_view_link=web_view,
            web_content_link=response.get("webContentLink"),
            created_time=response.get("createdTime", ""),
        )

        logger.info(
            "upload_file: file_id=%s name=%s mime_type=%s size=%d has_web_content=%s",
            _mask_id(uploaded.file_id),
            uploaded.name,
            uploaded.mime_type,
            uploaded.size,
            "yes" if uploaded.web_content_link else "no",
        )
        return uploaded

    def upload_csv(
        self,
        *,
        filename: str,
        csv_bytes: bytes,
        app_properties: dict[str, str],
    ) -> DriveUploadedFile:
        return self.upload_file(
            filename=filename,
            file_bytes=csv_bytes,
            mime_type="text/csv",
            app_properties=app_properties,
        )
