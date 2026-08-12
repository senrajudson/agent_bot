from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class DeliveryMode(str, Enum):
    INLINE = "inline"
    DRIVE_ARTIFACT = "drive_artifact"
    REJECT = "reject"


@dataclass(frozen=True)
class DeliveryDecision:
    mode: DeliveryMode
    reason: str
    reason_code: str | None = None
    suggested_format: str = "csv"


@dataclass(frozen=True)
class RequestSummary:
    tool_name: str
    tags_requested: int = 0
    tags_processed: int = 0
    start_time: str = ""
    end_time: str = ""
    operation: str = ""
    group_by: str | None = None
    output_mode: str | None = None
    data_method: str | None = None
    lookback_minutes: int | None = None
    environment: str | None = None


@dataclass(frozen=True)
class ArtifactMetadata:
    format: str
    filename: str
    mime_type: str
    row_count: int
    column_count: int
    size_bytes: int
    view_url: str


@dataclass(frozen=True)
class ErrorsSummaryItem:
    tag: str | None = None
    code: str = ""
    message: str = ""
    retryable: bool = False


@dataclass(frozen=True)
class WarningsItem:
    code: str = ""
    message: str = ""
    tag: str | None = None


@dataclass(frozen=True)
class ArtifactManifest:
    schema_version: str = "1.0"
    status: str = "success"
    delivery: str = "drive_artifact"
    tool_name: str = ""
    request_summary: RequestSummary | None = None
    artifact: ArtifactMetadata | None = None
    warnings: list[WarningsItem] = field(default_factory=list)
    errors_summary: list[ErrorsSummaryItem] = field(default_factory=list)
    items_omitted: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return self._serializable()

    def to_json(self, *, ensure_ascii: bool = False) -> str:
        return json.dumps(
            self._serializable(),
            ensure_ascii=ensure_ascii,
            separators=(",", ":"),
        )

    def fits_in(self, max_bytes: int) -> bool:
        return len(self.to_json().encode("utf-8")) <= max_bytes

    def _serializable(self) -> dict[str, Any]:
        d = {}
        d["schema_version"] = self.schema_version
        d["status"] = self.status
        d["delivery"] = self.delivery
        d["tool_name"] = self.tool_name
        if self.request_summary is not None:
            d["request_summary"] = asdict(self.request_summary)
        if self.artifact is not None:
            d["artifact"] = asdict(self.artifact)
        if self.warnings:
            d["warnings"] = [
                {key: value for key, value in asdict(w).items() if value is not None}
                for w in self.warnings
            ]
        if self.errors_summary:
            d["errors_summary"] = [asdict(e) for e in self.errors_summary]
        if self.items_omitted is not None:
            d["items_omitted"] = self.items_omitted
        return d
