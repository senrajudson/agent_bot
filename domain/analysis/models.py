from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

ZeroPolicy = Literal["valid", "suspicious", "invalid"]
PointType = Literal["numeric", "digital"]
QualityVerdict = Literal[
    "DADOS_EXCELENTES",
    "DADOS_SAUDÁVEIS",
    "DADOS_ACEITÁVEIS",
    "DADOS_DEGRADADOS",
]


class DigitalAnalysisStatus(str, Enum):
    COMPLETE = "complete"
    NO_TRANSITIONS = "no_transitions"
    PARTIAL_COVERAGE = "partial_coverage"
    NO_DATA = "no_data"
    INVALID_DIGITAL_VALUES = "invalid_digital_values"


class SegmentKind(str, Enum):
    KNOWN = "known"
    BAD = "bad"
    UNKNOWN = "unknown"
    NULL = "null"
    UNCOVERED = "uncovered"


class SegmentSource(str, Enum):
    SEED_AT_OR_BEFORE = "seed_at_or_before"
    RECORDED = "recorded"


class LimitStatus(str, Enum):
    NOT_REACHED = "NOT_REACHED"
    REACHED_EXACT = "REACHED_EXACT"
    EXCEEDED = "EXCEEDED"
    REACHED_UNCONFIRMED = "REACHED_UNCONFIRMED"


class AnalysisCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    COMPLETENESS_UNCONFIRMED = "COMPLETENESS_UNCONFIRMED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AnalysisCompletenessMetadata:
    requested_start_time: str
    requested_end_time: str
    effective_start_time: str
    effective_end_time: str
    returned_point_count: int
    configured_point_limit: int
    pi_request_safe_limit: int
    artifact_safe_row_limit: int
    effective_point_limit: int
    limit_status: LimitStatus
    analysis_completeness: AnalysisCompleteness
    truncated: Optional[bool]
    truncation_direction: str = "FROM_WINDOW_START"
    overflow_check_performed: bool = False
    unprocessed_start_time: Optional[str] = None
    unprocessed_end_time: Optional[str] = None


@dataclass(frozen=True)
class AnalysisRequest:
    tag: str = ""
    tags: tuple[str, ...] = ()
    start_time: str = ""
    end_time: str = ""
    zero_policy: ZeroPolicy = "suspicious"


@dataclass(frozen=True)
class TagMetadata:
    tag: str
    point_type: PointType
    descriptor: str = ""
    engineering_units: Optional[str] = None
    digital_set: Optional[str] = None


@dataclass(frozen=True)
class AnalysisPoint:
    timestamp: str
    value: Optional[float]
    good: bool = True
    questionable: bool = False
    substituted: bool = False


@dataclass(frozen=True)
class QualityMetrics:
    good_pct: float
    questionable_pct: float
    substituted_pct: float
    zero_pct: float
    verdict: QualityVerdict


@dataclass(frozen=True)
class NumericStatistics:
    count: int
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    p01: Optional[float] = None
    p99: Optional[float] = None
    stddev_pop: Optional[float] = None
    stddev_sample: Optional[float] = None
    sum: Optional[float] = None
    zero_count: int = 0


@dataclass(frozen=True)
class GapCandidate:
    method: Literal["interpolated", "recorded"]
    start_ts: str
    end_ts: str
    duration_seconds: float


@dataclass(frozen=True)
class AbruptChangeCandidate:
    timestamp: str
    previous_value: float
    current_value: float
    absolute_delta: float
    relative_delta: float
    detection_basis: Literal["zscore", "relative", "both"]


@dataclass(frozen=True)
class DigitalStateDuration:
    state: str
    count: int
    percent: float
    duration_seconds: float


@dataclass(frozen=True)
class DigitalTransition:
    from_state: str
    to_state: str
    count: int
    rate_per_hour: float


@dataclass(frozen=True)
class DigitalStateRef:
    state_code: int | str
    state_name: str


@dataclass(frozen=True)
class DigitalStateOccupancy:
    state_code: int | str
    state_name: str
    duration_seconds: float
    percentage_of_window: float
    entries_count: int


@dataclass(frozen=True)
class DigitalCoverageMetrics:
    window_seconds: float
    known_seconds: float
    known_pct: float
    bad_seconds: float
    bad_pct: float
    null_seconds: float
    null_pct: float
    unknown_seconds: float
    unknown_pct: float
    uncovered_seconds: float
    uncovered_pct: float
    questionable_seconds: float
    questionable_pct: float
    substituted_seconds: float
    substituted_pct: float


# ---------------------------------------------------------------------------
# Novos tipos para relatório digital auditável
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimelineSegment:
    start: object
    end: object
    duration_seconds: float
    raw_value: float | int | None
    state_code: int | str | None
    state_name: str | None
    kind: SegmentKind
    good: bool | None
    questionable: bool | None
    substituted: bool | None
    source: SegmentSource | None


@dataclass(frozen=True)
class DigitalRecordedEvent:
    timestamp: str
    raw_value: float | None
    resolved_code: int | None
    resolved_state: str | None
    classification: SegmentKind
    good: bool
    questionable: bool
    substituted: bool


@dataclass(frozen=True)
class SeedInfo:
    found: bool
    timestamp: str | None
    raw_value: float | None
    good: bool | None
    questionable: bool | None
    substituted: bool | None
    classification: SegmentKind | None
    age_seconds_at_window_start: float | None
    state_code: int | str | None
    state_name: str | None


@dataclass(frozen=True)
class StateStatistic:
    state_code: int | str
    state_name: str
    observed: bool
    entries_count: int
    exits_count: int
    segment_count: int
    duration_seconds: float
    percentage_of_window: float
    first_seen: object
    last_seen: object
    longest_segment_start: object
    longest_segment_end: object
    dwell_avg_seconds: float | None
    dwell_median_seconds: float | None
    dwell_min_seconds: float | None
    dwell_max_seconds: float | None


@dataclass(frozen=True)
class TransitionStatistic:
    from_kind: SegmentKind | None
    from_code: int | str | None
    from_name: str | None
    to_kind: SegmentKind | None
    to_code: int | str | None
    to_name: str | None
    count: int
    first_transition: object
    last_transition: object
    percentage_of_transitions: float


@dataclass(frozen=True)
class UnknownValueStatistic:
    raw_value: float | int
    occurrences: int
    segment_count: int
    duration_seconds: float
    percentage_of_window: float
    first_seen: object
    last_seen: object
    sample_timestamp: str | None


@dataclass(frozen=True)
class QualitySummary:
    total_events: int
    good_events: int
    bad_events: int
    questionable_events: int
    substituted_events: int
    known_duration: float
    bad_duration: float
    unknown_duration: float
    null_duration: float
    uncovered_duration: float
    questionable_duration: float
    questionable_pct: float
    substituted_duration: float
    substituted_pct: float
    bad_segment_count: int
    unknown_segment_count: int
    longest_bad_start: object
    longest_bad_end: object
    longest_bad_duration: float
    longest_unknown_start: object
    longest_unknown_end: object
    longest_unknown_duration: float
    first_bad_timestamp: str | None
    last_bad_timestamp: str | None


@dataclass(frozen=True)
class DailyBucket:
    date: str
    known_pct: float
    bad_pct: float
    unknown_pct: float
    null_pct: float
    uncovered_pct: float
    transition_count: int
    dominant_state_code: int | str | None
    dominant_state_name: str | None
    dominant_state_pct: float | None
    distinct_states_observed: int
    distinct_unknown_values: int


@dataclass(frozen=True)
class DigitalSetSnapshotEntry:
    state_code: int | str
    state_name: str
    state_description: str | None


@dataclass(frozen=True)
class DigitalDiagnosticWarning:
    code: str
    severity: str


# ---------------------------------------------------------------------------
# DigitalAnalysisResult (ampliado com defaults retrocompatíveis)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DigitalAnalysisResult:
    status: DigitalAnalysisStatus
    possible_states: tuple[DigitalStateRef, ...]
    initial_state: Optional[DigitalStateRef]
    final_state: Optional[DigitalStateRef]
    occupancy: tuple[DigitalStateOccupancy, ...]
    transitions: tuple[DigitalTransition, ...]
    coverage: DigitalCoverageMetrics
    recorded_events_count: int
    valid_events_count: int
    warnings: tuple[str, ...] = ()
    # Novos campos (defaults retrocompatíveis)
    timeline_segments: tuple[TimelineSegment, ...] = ()
    classified_recorded_events: tuple[DigitalRecordedEvent, ...] = ()
    seed_info: Optional[SeedInfo] = None
    state_statistics: tuple[StateStatistic, ...] = ()
    transition_statistics: tuple[TransitionStatistic, ...] = ()
    unknown_value_statistics: tuple[UnknownValueStatistic, ...] = ()
    quality_summary: Optional[QualitySummary] = None
    daily_summary: tuple[DailyBucket, ...] = ()
    digital_set_snapshot: tuple[DigitalSetSnapshotEntry, ...] = ()
    diagnostic_warnings: tuple[DigitalDiagnosticWarning, ...] = ()


@dataclass(frozen=True)
class TagAnalysisResult:
    metadata: TagMetadata
    quality: Optional[QualityMetrics] = None
    digital_analysis: Optional[DigitalAnalysisResult] = None
    start_time: str = ""
    end_time: str = ""
    numeric: Optional[NumericStatistics] = None
    digital_durations: tuple[DigitalStateDuration, ...] = ()
    digital_transitions: tuple[DigitalTransition, ...] = ()
    gaps_interpolated: tuple[GapCandidate, ...] = ()
    gaps_recorded: tuple[GapCandidate, ...] = ()
    spikes: tuple[AbruptChangeCandidate, ...] = ()
    spike_total_count: int = 0
    zero_policy_applied: ZeroPolicy = "suspicious"
    warnings: tuple[str, ...] = ()
    zero_policy_warning: Optional[str] = None
    completeness: Optional[AnalysisCompletenessMetadata] = None


@dataclass(frozen=True)
class AnalysisError:
    tag: Optional[str] = None
    code: str = ""
    message: str = ""
    retryable: bool = False


@dataclass(frozen=True)
class MultiTagAnalysisResult:
    results: tuple[TagAnalysisResult, ...] = ()
    errors: tuple[AnalysisError, ...] = ()
    period_start: str = ""
    period_end: str = ""
    total_requested: int = 0
    total_processed: int = 0
    overall_completeness: Optional[AnalysisCompleteness] = None
