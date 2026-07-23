from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    expires_at: datetime
    cleanup_after_send: bool = False
    kind: str = "artifact"
    owner: str | None = None

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError(
                "created_at must be timezone-aware (UTC). "
                f"Got: {self.created_at}"
            )
        if self.expires_at.tzinfo is None:
            raise ValueError(
                "expires_at must be timezone-aware (UTC). "
                f"Got: {self.expires_at}"
            )

    def is_expired(self, now: datetime | None = None) -> bool:
        ref = now or now_utc()
        return ref >= self.expires_at
