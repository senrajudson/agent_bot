from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Literal
from zoneinfo import ZoneInfo

from domain.shared.errors import DomainValidationError, ValidationErrorCode


DEFAULT_PI_TIMEZONE = "America/Sao_Paulo"

TimeInputKind = Literal["relative", "absolute", "mixed"]

_TOKEN_STAR = re.compile(r"^\*$")
_TOKEN_STAR_N_HOURS = re.compile(r"^\*-(\d+)\s*h$")
_TOKEN_STAR_N_DAYS = re.compile(r"^\*-(\d+)\s*d$")
_TOKEN_T = re.compile(r"^[Tt]$")
_TOKEN_Y = re.compile(r"^[Yy]$")


@dataclass(frozen=True)
class ResolvedTimeRange:
    start: datetime
    end: datetime
    start_iso: str
    end_iso: str
    timezone: str
    input_kind: TimeInputKind

    @property
    def window_seconds(self) -> int:
        return int((self.end - self.start).total_seconds())


def _is_iso_with_offset(token: str) -> bool:
    try:
        dt = datetime.fromisoformat(token)
        return dt.tzinfo is not None
    except (ValueError, TypeError):
        return False


def _resolve_one(token: str, now: datetime, tz: ZoneInfo) -> datetime:
    if _TOKEN_STAR.match(token):
        return now
    if m := _TOKEN_STAR_N_HOURS.match(token):
        return now - timedelta(hours=int(m.group(1)))
    if m := _TOKEN_STAR_N_DAYS.match(token):
        return now - timedelta(days=int(m.group(1)))
    if _TOKEN_T.match(token):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if _TOKEN_Y.match(token):
        return (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if _is_iso_with_offset(token):
        dt = datetime.fromisoformat(token)
        return dt.astimezone(tz)
    if not token or token.strip() == "":
        raise DomainValidationError(
            ValidationErrorCode.INVALID_TIME_EXPRESSION,
            "Expressão temporal vazia.",
        )
    raise DomainValidationError(
        ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION,
        f"Expressão temporal não suportada: '{token}'.",
    )


def _classify_input_kind(start: str, end: str) -> TimeInputKind:
    def _is_relative(t: str) -> bool:
        if not t or t.strip() == "":
            return False
        if _TOKEN_STAR.match(t):
            return True
        if _TOKEN_STAR_N_HOURS.match(t):
            return True
        if _TOKEN_STAR_N_DAYS.match(t):
            return True
        if _TOKEN_T.match(t):
            return True
        if _TOKEN_Y.match(t):
            return True
        return False

    start_rel = _is_relative(start)
    end_rel = _is_relative(end)
    if start_rel and end_rel:
        return "relative"
    if not start_rel and not end_rel:
        return "absolute"
    return "mixed"


def resolve_pi_time_range(
    start_time: str,
    end_time: str,
    *,
    timezone: str | ZoneInfo = DEFAULT_PI_TIMEZONE,
    now: datetime | None = None,
) -> ResolvedTimeRange:
    tz = ZoneInfo(timezone) if isinstance(timezone, str) else timezone

    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        raise DomainValidationError(
            ValidationErrorCode.TIME_RESOLUTION_ERROR,
            "O parâmetro 'now' deve ser timezone-aware.",
        )
    else:
        now = now.astimezone(tz)

    if not start_time or not start_time.strip():
        raise DomainValidationError(
            ValidationErrorCode.INVALID_TIME_EXPRESSION,
            "start_time não pode ser vazio.",
        )

    try:
        start_dt = _resolve_one(start_time.strip(), now, tz)
        end_dt = _resolve_one(end_time.strip(), now, tz)
    except DomainValidationError:
        raise
    except Exception as exc:
        raise DomainValidationError(
            ValidationErrorCode.TIME_RESOLUTION_ERROR,
            f"Erro inesperado ao resolver expressão temporal: {exc}",
        ) from exc

    if start_dt >= end_dt:
        raise DomainValidationError(
            ValidationErrorCode.INVALID_TIME_WINDOW,
            f"start_time ({start_dt.isoformat()}) deve ser anterior a "
            f"end_time ({end_dt.isoformat()}).",
        )

    input_kind = _classify_input_kind(start_time, end_time)

    return ResolvedTimeRange(
        start=start_dt,
        end=end_dt,
        start_iso=start_dt.isoformat(),
        end_iso=end_dt.isoformat(),
        timezone=str(tz),
        input_kind=input_kind,
    )
