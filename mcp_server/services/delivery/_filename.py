import re
import uuid
from datetime import datetime, timezone


def build_filename(
    environment: str,
    tool: str,
    extension: str,
    *,
    now: datetime | None = None,
) -> str:
    sanitized_env = re.sub(r"[^A-Za-z0-9_.-]", "_", str(environment))
    sanitized_tool = re.sub(r"[^A-Za-z0-9_.-]", "_", str(tool))
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    short_id = uuid.uuid4().hex[:8]
    return f"pi_chat_{sanitized_env}_{sanitized_tool}_{ts}_{short_id}.{extension}"
