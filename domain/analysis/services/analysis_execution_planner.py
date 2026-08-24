from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from domain.analysis.models import AnalysisRequest, MetricExecutionKind
from domain.analysis.policies import (
    ALLOWED_ANALYSIS_TYPES,
    validate_analysis_types,
    validate_calculation_basis,
    validate_interval,
)
from domain.shared.errors import DomainValidationError, ValidationErrorCode

_PI_SUMMARY_METRICS = {
    "mean": "Average",
    "min": "Minimum",
    "max": "Maximum",
    "count": "Count",
    "stddev_sample": "StdDev",
    "stddev_pop": "PopulationStdDev",
    "range": "Range",
    "percent_good": "PercentGood",
    "sum": "Total",
}

_LOCAL_ONLY_METRICS = {
    "median", "p01", "p99", "quality", "gaps", "spikes", "recorded", "interpolated"
}

_PI_CALCULATION_METRICS = {
    "zero_count", "digital_states"
}


@dataclass(frozen=True)
class ExecutionPlan:
    request: AnalysisRequest
    resolved_analysis_types: tuple[str, ...]
    pi_summary_types: tuple[str, ...]
    needs_recorded: bool
    needs_interpolated: bool
    needs_local_metrics: bool
    metric_kinds: dict[str, MetricExecutionKind]
    estimated_rows: int


class AnalysisExecutionPlanner:
    def create_plan(self, request: AnalysisRequest) -> ExecutionPlan:
        resolved = validate_analysis_types(request.analysis_types)
        interval = validate_interval(request.interval)
        calc_basis = validate_calculation_basis(request.calculation_basis)

        if "all" in resolved:
            effective_metrics = [m for m in ALLOWED_ANALYSIS_TYPES if m != "all"]
        else:
            effective_metrics = list(resolved)

        pi_summary_types_set: set[str] = set()
        metric_kinds: dict[str, MetricExecutionKind] = {}

        needs_recorded = False
        needs_interpolated = False
        needs_local_metrics = False

        for m in effective_metrics:
            if m in _PI_SUMMARY_METRICS:
                # Se zero_policy for invalid e m for estatística direta que pode incluir zeros sem filtragem
                if request.zero_policy == "invalid" and m in ("mean", "sum", "count", "stddev_sample", "stddev_pop"):
                    # Não pode usar summary direta se incluir zeros; cairá para fallback ou local conforme política
                    pass
                
                pi_summary_types_set.add(_PI_SUMMARY_METRICS[m])
                metric_kinds[m] = MetricExecutionKind.PI_SUMMARY
            elif m in _LOCAL_ONLY_METRICS:
                metric_kinds[m] = MetricExecutionKind.LOCAL_ONLY
                needs_local_metrics = True
                if m in ("gaps", "spikes", "recorded"):
                    needs_recorded = True
                if m in ("interpolated", "median", "p01", "p99"):
                    needs_interpolated = True
            elif m in _PI_CALCULATION_METRICS:
                metric_kinds[m] = MetricExecutionKind.PI_CALCULATION
            else:
                metric_kinds[m] = MetricExecutionKind.UNSUPPORTED

        # Se requested "all", precisa de séries para Recorded, Interpolated, Gaps, Spikes e Qualidade
        if "all" in resolved:
            needs_recorded = True
            needs_interpolated = True
            needs_local_metrics = True

        tag_count = len(request.tags) if request.tags else (1 if request.tag else 1)
        estimated_buckets = 1
        if interval:
            estimated_buckets = 100  # Estimativa prudente
        estimated_rows = tag_count * len(effective_metrics) * estimated_buckets

        if estimated_rows > 150_000:
            raise DomainValidationError(
                code=ValidationErrorCode.ESTIMATED_ROW_LIMIT_EXCEEDED,
                message=f"Estimativa de linhas do relatório ({estimated_rows}) excede o limite seguro de 150.000.",
            )


        return ExecutionPlan(
            request=request,
            resolved_analysis_types=tuple(effective_metrics),
            pi_summary_types=tuple(sorted(pi_summary_types_set)),
            needs_recorded=needs_recorded,
            needs_interpolated=needs_interpolated,
            needs_local_metrics=needs_local_metrics,
            metric_kinds=metric_kinds,
            estimated_rows=estimated_rows,
        )
