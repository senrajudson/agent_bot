from __future__ import annotations

from typing import Any

from mcp_server.services.delivery.contracts import (
    ArtifactManifest,
    ArtifactMetadata,
    ErrorsSummaryItem,
    RequestSummary,
    WarningsItem,
)
from mcp_server.services.delivery.exceptions import ManifestSizeExceededError

_MAX_WARNINGS = 10
_MAX_ERRORS = 10
_MAX_MESSAGE_CHARS = 300
_DEFAULT_MAX_MANIFEST_BYTES = 8_192


def _truncate_list(
    items: list[Any],
    max_count: int,
    max_msg_chars: int = _MAX_MESSAGE_CHARS,
) -> list[Any]:
    result = []
    for item in items:
        truncated = _truncate_message(item, max_msg_chars)
        result.append(truncated)
    return result[:max_count]


def _truncate_message(item: Any, max_chars: int) -> Any:
    if isinstance(item, (ErrorsSummaryItem, WarningsItem)):
        d = item.__dict__.copy()
        if len(d.get("message", "") or "") > max_chars:
            d["message"] = d["message"][:max_chars] + "..."
        return item.__class__(**d)
    return item


def build_artifact_manifest(
    *,
    status: str,
    tool_name: str,
    request_summary: RequestSummary,
    artifact_metadata: ArtifactMetadata | None = None,
    warnings: list[WarningsItem] | None = None,
    errors_summary: list[ErrorsSummaryItem] | None = None,
    max_manifest_bytes: int = _DEFAULT_MAX_MANIFEST_BYTES,
) -> ArtifactManifest:
    safe_warnings = _truncate_list(warnings or [], _MAX_WARNINGS)
    safe_errors = _truncate_list(errors_summary or [], _MAX_ERRORS)
    original_warnings_count = len(warnings or [])
    original_errors_count = len(errors_summary or [])
    omitted = 0
    if len(safe_warnings) < original_warnings_count:
        omitted += original_warnings_count - len(safe_warnings)
    if len(safe_errors) < original_errors_count:
        omitted += original_errors_count - len(safe_errors)

    delivery = "drive_artifact" if artifact_metadata is not None else "inline"

    manifest = ArtifactManifest(
        status=status,
        delivery=delivery,
        tool_name=tool_name,
        request_summary=request_summary,
        artifact=artifact_metadata,
        warnings=safe_warnings,
        errors_summary=safe_errors,
        items_omitted=omitted if omitted > 0 else None,
    )

    if not manifest.fits_in(max_manifest_bytes):
        while safe_warnings or safe_errors:
            if safe_errors:
                safe_errors.pop()
            elif safe_warnings:
                safe_warnings.pop()
            manifest = ArtifactManifest(
                status=status,
                delivery=delivery,
                tool_name=tool_name,
                request_summary=request_summary,
                artifact=artifact_metadata,
                warnings=safe_warnings,
                errors_summary=safe_errors,
                items_omitted=omitted + (original_errors_count - len(safe_errors)) + (original_warnings_count - len(safe_warnings)),
            )
            if manifest.fits_in(max_manifest_bytes):
                break
        else:
            raise ManifestSizeExceededError(
                f"Manifest ultrapassou {max_manifest_bytes} bytes mesmo sem warnings/errors."
            )

    return manifest
