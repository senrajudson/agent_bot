"""Immutable value objects representing domain concepts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TimeUnitValue(str, Enum):
    """Valid time units for calculus results."""

    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    NONE = "none"


class SummaryTypeValue(str, Enum):
    """Valid aggregation types for summary queries."""

    AVERAGE = "Average"
    MINIMUM = "Minimum"
    MAXIMUM = "Maximum"
    RANGE = "Range"
    STDDEV = "StdDev"
    TOTAL = "Total"
    COUNT = "Count"


class CalculationBasisValue(str, Enum):
    """Valid calculation bases for summary queries."""

    TIME_WEIGHTED = "TimeWeighted"
    EVENT_WEIGHTED = "EventWeighted"


@dataclass(frozen=True)
class PiWebId:
    """Immutable identifier of a PI Point on the PI Web API.

    Obtained via /points?path=... and used for all stream endpoints.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not isinstance(self.value, str):
            raise ValueError("PiWebId must be a non-empty string")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EngineeringUnit:
    """Engineering unit of a tag (e.g., 'Nm3/h', '°C', 'bar')."""

    value: str

    def __post_init__(self) -> None:
        if self.value is None:
            raise ValueError("EngineeringUnit cannot be None")

    def __str__(self) -> str:
        return self.value or "(no unit)"


@dataclass(frozen=True)
class TimeWindow:
    """Temporal window (start, end) for a PI query.

    Accepts either ISO 8601 with offset or PI relative syntax ('*-7d').
    """

    start: str
    end: str

    def __post_init__(self) -> None:
        if not self.start or not self.end:
            raise ValueError("TimeWindow requires both start and end")
        if not isinstance(self.start, str) or not isinstance(self.end, str):
            raise ValueError("TimeWindow bounds must be strings")

    def with_default_end(self) -> TimeWindow:
        """Returns a copy with end='*' (now) if end is empty."""
        return TimeWindow(start=self.start, end=self.end or "*")


@dataclass(frozen=True)
class TimeUnit:
    """Temporal unit for calculus results (second, minute, hour, none)."""

    value: TimeUnitValue

    @classmethod
    def from_string(cls, s: str | None) -> TimeUnit:
        """Safe factory — returns NONE for None or unknown values."""
        if not s:
            return cls(TimeUnitValue.NONE)
        try:
            return cls(TimeUnitValue(s.lower()))
        except ValueError:
            return cls(TimeUnitValue.NONE)

    def __str__(self) -> str:
        return self.value.value


@dataclass(frozen=True)
class SummaryType:
    """Type of aggregation for summary queries."""

    value: SummaryTypeValue

    @classmethod
    def from_string(cls, s: str | None) -> SummaryType:
        """Safe factory with default Average."""
        if not s:
            return cls(SummaryTypeValue.AVERAGE)
        try:
            return cls(SummaryTypeValue(s))
        except ValueError:
            return cls(SummaryTypeValue.AVERAGE)

    def __str__(self) -> str:
        return self.value.value


@dataclass(frozen=True)
class CalculationBasis:
    """Calculation basis for summary queries."""

    value: CalculationBasisValue

    @classmethod
    def from_string(cls, s: str | None) -> CalculationBasis:
        """Safe factory with default TimeWeighted."""
        if not s:
            return cls(CalculationBasisValue.TIME_WEIGHTED)
        try:
            return cls(CalculationBasisValue(s))
        except ValueError:
            return cls(CalculationBasisValue.TIME_WEIGHTED)

    def __str__(self) -> str:
        return self.value.value


# ---------------------------------------------------------------------------
# Identity Value Object: ConversationId
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConversationId:
    """Immutable identifier of a conversation.

    Derived from user_id (Prompt 3 Ciclo 1). Preserves current behavior:
    conversation_id = user_id, with "anonymous" as fallback when user_id is
    None or empty. Validates non-empty/non-None at construction time.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("ConversationId value must be a str")
        if not self.value:
            raise ValueError("ConversationId must be a non-empty string")

    @classmethod
    def from_user_id(cls, user_id: str | None) -> "ConversationId":
        """Derive ConversationId from user_id (or None).

        Preserves current production behavior: if user_id is None or empty,
        returns ConversationId("anonymous"). Otherwise returns
        ConversationId(user_id).

        NOTE: whitespace-only user_id is currently accepted (debt — should
        be rejected in future).
        """
        if not user_id:
            return cls("anonymous")
        return cls(user_id)

    def __str__(self) -> str:
        return self.value
