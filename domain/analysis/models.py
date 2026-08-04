from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

ZeroPolicy = Literal["valid", "suspicious", "invalid"]
PointType = Literal["numeric", "digital"]
QualityVerdict = Literal[
    "DADOS_EXCELENTES",
    "DADOS_SAUDÁVEIS",
    "DADOS_ACEITÁVEIS",
    "DADOS_DEGRADADOS",
]


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
class TagAnalysisResult:
    metadata: TagMetadata
    quality: QualityMetrics
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
