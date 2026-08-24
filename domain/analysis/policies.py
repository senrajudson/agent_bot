from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from domain.analysis.models import QualityVerdict, ZeroPolicy
from domain.shared.errors import DomainValidationError, ValidationErrorCode

ZERO_POLICIES: tuple[ZeroPolicy, ...] = ("valid", "suspicious", "invalid")

QUALITY_THRESHOLDS: dict[QualityVerdict, dict[str, object]] = {
    "DADOS_EXCELENTES": {
        "good_min": 99.0,
        "questionable_max": 0.0,
        "substituted_max": 0.0,
        "zero_pct_max_strict": 5.0,
    },
    "DADOS_SAUDÁVEIS": {
        "good_min": 95.0,
        "questionable_max": 1.0,
        "substituted_max": 1.0,
    },
    "DADOS_ACEITÁVEIS": {
        "good_min": 80.0,
    },
}

GAP_THRESHOLD_INTERPOLATED_SECONDS = 900
GAP_THRESHOLD_RECORDED_FALLBACK_SECONDS = 1800
EXPECTED_INTERPOLATED_INTERVAL_SECONDS = 300

SPIKE_ROLLING_WINDOW = 5
SPIKE_RELATIVE_DELTA = 0.5
SPIKE_TOP_N = 5

INLINE_MAX_GAPS = 5
INLINE_MAX_SPIKES = 5
INLINE_MAX_STATES = 10
INLINE_MAX_TRANSITIONS = 5

PROHIBITED_VERDICT_TERMS = (
    "processo",
    "equipamento",
    "operador",
    "produto",
    "manutenção",
    "defeito",
    "anomalia confirmada",
    "causa raiz",
    "normal",
    "anormal",
    "saudável",
    "defeituoso",
)

MAX_TAGS = 10
MAX_PERIOD_DAYS = 31
_ERROR_CODES = {
    "MISSING_TAG",
    "MISSING_TAGS",
    "TOO_MANY_TAGS",
    "INVALID_TIME_WINDOW",
    "WINDOW_EXCEEDS_MAX",
    "INVALID_TIMESTAMP",
    "TAG_NOT_FOUND",
    "PI_TIMEOUT",
    "PI_AUTH_ERROR",
    "NO_DATA_IN_WINDOW",
    "INVALID_DIGITAL_SET",
    "UNSUPPORTED_POINT_TYPE",
    "PI_RESPONSE_INVALID",
}


def assess_quality(
    good_pct: float,
    questionable_pct: float,
    substituted_pct: float,
    zero_pct: float,
    zero_policy: ZeroPolicy,
) -> QualityVerdict:
    if (
        good_pct >= 99.0
        and questionable_pct == 0.0
        and substituted_pct == 0.0
        and (zero_pct < 5.0 or zero_policy == "valid")
    ):
        return "DADOS_EXCELENTES"
    if (
        good_pct >= 95.0
        and questionable_pct <= 1.0
        and substituted_pct <= 1.0
    ):
        return "DADOS_SAUDÁVEIS"
    if good_pct >= 80.0:
        return "DADOS_ACEITÁVEIS"
    return "DADOS_DEGRADADOS"


ALLOWED_ANALYSIS_TYPES: tuple[str, ...] = (
    "all", "mean", "min", "max", "count", "sum", "stddev_sample", "stddev_pop",
    "range", "percent_good", "median", "p01", "p99", "zero_count", "quality",
    "gaps", "spikes", "recorded", "interpolated", "digital_states",
)

INTERVAL_REGEX = re.compile(r"^[1-9][0-9]*[smhd]$")


def validate_analysis_types(
    types: Optional[tuple[str, ...] | list[str]]
) -> tuple[str, ...]:
    if types is None:
        return ("all",)
    if len(types) == 0:
        raise DomainValidationError(
            code=ValidationErrorCode.INVALID_ARGUMENT_COMBINATION,
            message="analysis_types não pode ser uma lista vazia.",
        )
    
    clean: list[str] = []
    seen: set[str] = set()
    for item in types:
        s = str(item).strip().lower()
        if s not in ALLOWED_ANALYSIS_TYPES:
            raise DomainValidationError(
                code=ValidationErrorCode.INVALID_ARGUMENT_COMBINATION,
                message=f"Tipo de análise inválido ou não suportado: {item!r}.",
            )
        if s not in seen:
            clean.append(s)
            seen.add(s)
            
    if "all" in clean:
        if len(clean) > 1:
            raise DomainValidationError(
                code=ValidationErrorCode.INVALID_ARGUMENT_COMBINATION,
                message="'all' não pode ser combinado com outras métricas em analysis_types.",
            )
        return ("all",)
        
    return tuple(clean)


def validate_interval(interval: Optional[str]) -> Optional[str]:
    if not interval:
        return None
    s = interval.strip().lower()
    if not INTERVAL_REGEX.match(s):
        raise DomainValidationError(
            code=ValidationErrorCode.INVALID_INTERVAL,
            message=f"Formato de interval inválido: {interval!r}. Use formato como '5m', '15m', '1h', '1d'.",
        )
    return s


def validate_calculation_basis(basis: str) -> str:
    s = basis.strip().lower()
    if s not in ("time_weighted", "event_weighted"):
        raise DomainValidationError(
            code=ValidationErrorCode.INVALID_ARGUMENT_COMBINATION,
            message=f"calculation_basis inválido: {basis!r}. Use 'time_weighted' ou 'event_weighted'.",
        )
    return s



def validate_analysis_report_contract(
    tags: tuple[str, ...] | list[str],
    start_time: str,
    end_time: str,
    *,
    zero_policy: Optional[ZeroPolicy] = None,
    analysis_types: Optional[tuple[str, ...] | list[str]] = None,
    interval: Optional[str] = None,
    calculation_basis: str = "time_weighted",
) -> None:
    if not tags:
        raise DomainValidationError(
            code=ValidationErrorCode.MISSING_TAGS,
            message="Pelo menos uma tag é obrigatória.",
        )

    clean: list[str] = []
    seen: set[str] = set()
    for t in tags:
        stripped = t.strip()
        if not stripped:
            raise DomainValidationError(
                code=ValidationErrorCode.MISSING_TAG,
                message="Tag vazia não é permitida.",
            )
        if stripped not in seen:
            clean.append(stripped)
            seen.add(stripped)

    if len(clean) > MAX_TAGS:
        raise DomainValidationError(
            code=ValidationErrorCode.TOO_MANY_TAGS,
            message=f"Máximo de {MAX_TAGS} tags permitido.",
        )

    if zero_policy is not None and zero_policy not in ZERO_POLICIES:
        raise DomainValidationError(
            code=ValidationErrorCode.INVALID_ZERO_POLICY,
            message=f"zero_policy deve ser um de {ZERO_POLICIES}.",
        )

    validate_analysis_types(analysis_types)
    validate_interval(interval)
    validate_calculation_basis(calculation_basis)

    _parse_iso(start_time, "start_time")
    _parse_iso(end_time, "end_time")

    start_dt = _parse_iso(start_time, "start_time")
    end_dt = _parse_iso(end_time, "end_time")

    if start_dt >= end_dt:
        raise DomainValidationError(
            code=ValidationErrorCode.INVALID_TIME_WINDOW,
            message="start_time deve ser anterior a end_time.",
        )



def _parse_iso(value: str, field_name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise DomainValidationError(
            code=ValidationErrorCode.INVALID_TIMESTAMP,
            message=f"{field_name} não é ISO 8601 válido: {value!r}",
        ) from exc
    if dt.tzinfo is None:
        raise DomainValidationError(
            code=ValidationErrorCode.INVALID_TIMESTAMP,
            message=f"{field_name} deve conter offset de timezone: {value!r}",
        )
    return dt
