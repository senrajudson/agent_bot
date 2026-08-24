from __future__ import annotations

from typing import Optional

from datetime import datetime

from domain.analysis.models import (
    AnalysisCompleteness,
    AnalysisError,
    AnalysisPoint,
    AnalysisRequest,
    DigitalStateDuration,
    DigitalTransition,
    GapCandidate,
    MultiTagAnalysisResult,
    NumericStatistics,
    QualityMetrics,
    TagAnalysisResult,
    TagMetadata,
    ZeroPolicy,
)
from domain.analysis.policies import (
    GAP_THRESHOLD_INTERPOLATED_SECONDS,
    SPIKE_RELATIVE_DELTA,
    SPIKE_ROLLING_WINDOW,
    SPIKE_TOP_N,
    assess_quality,
    validate_analysis_report_contract,
)
from domain.analysis.services._digital import (
    compute_state_durations,
    compute_transitions,
    enrich_digital_result,
    reconstruct_timeline,
)
from domain.analysis.services._numeric import (
    compute_numeric_stats,
    detect_gaps_interpolated,
    detect_gaps_recorded,
    detect_spikes,
)
from domain.shared.errors import DomainValidationError


class TagAnalysisService:
    def validate_request(self, request: AnalysisRequest) -> None:
        if request.tag and not request.tags:
            tags = (request.tag,)
        elif request.tags:
            tags = request.tags
        else:
            tags = ()

        validate_analysis_report_contract(
            tags,
            request.start_time,
            request.end_time,
            zero_policy=request.zero_policy,
            analysis_types=request.analysis_types,
            interval=request.interval,
            calculation_basis=request.calculation_basis,
        )

    def analyze_one(
        self, data: CollectedData, request: AnalysisRequest
    ) -> TagAnalysisResult:
        metadata = data.metadata
        points = data.recorded + data.interpolated
        zero_policy = request.zero_policy

        if metadata.point_type == "digital":
            res = self._analyze_digital(data, request, zero_policy)
        else:
            res = self._analyze_numeric(points, metadata, request, zero_policy)

        # Injetar completude da coleta e bucket_summaries
        res = TagAnalysisResult(
            metadata=res.metadata,
            quality=res.quality,
            digital_analysis=res.digital_analysis,
            start_time=res.start_time,
            end_time=res.end_time,
            numeric=res.numeric,
            digital_durations=res.digital_durations,
            digital_transitions=res.digital_transitions,
            gaps_interpolated=res.gaps_interpolated,
            gaps_recorded=res.gaps_recorded,
            spikes=res.spikes,
            spike_total_count=res.spike_total_count,
            zero_policy_applied=res.zero_policy_applied,
            warnings=res.warnings,
            zero_policy_warning=res.zero_policy_warning,
            completeness=data.completeness or res.completeness,
            bucket_summaries=tuple(data.bucket_summaries),
        )

        return res

    def analyze_many(
        self,
        collected: dict[str, CollectedData | AnalysisError],
        request: AnalysisRequest,
    ) -> MultiTagAnalysisResult:
        results: list[TagAnalysisResult] = []
        errors: list[AnalysisError] = []

        for tag, data in collected.items():
            if isinstance(data, AnalysisError):
                errors.append(data)
                continue

            try:
                result = self.analyze_one(
                    data,
                    AnalysisRequest(
                        tag=tag,
                        start_time=request.start_time,
                        end_time=request.end_time,
                        zero_policy=request.zero_policy,
                        analysis_types=request.analysis_types,
                        interval=request.interval,
                        calculation_basis=request.calculation_basis,
                    ),
                )
                results.append(result)

            except Exception as exc:
                errors.append(
                    AnalysisError(
                        tag=tag,
                        code="ANALYSIS_INTERNAL_ERROR",
                        message=str(exc)[:300],
                        retryable=False,
                    )
                )

        # T030: Agregação de completude multitag
        if not results:
            overall = AnalysisCompleteness.FAILED
        elif any(r.completeness and r.completeness.analysis_completeness == AnalysisCompleteness.PARTIAL for r in results):
            overall = AnalysisCompleteness.PARTIAL
        elif any(r.completeness and r.completeness.analysis_completeness == AnalysisCompleteness.COMPLETENESS_UNCONFIRMED for r in results):
            overall = AnalysisCompleteness.COMPLETENESS_UNCONFIRMED
        else:
            overall = AnalysisCompleteness.COMPLETE

        return MultiTagAnalysisResult(
            results=tuple(results),
            errors=tuple(errors),
            period_start=request.start_time,
            period_end=request.end_time,
            total_requested=len(collected),
            total_processed=len(results),
            overall_completeness=overall,
        )

    def _analyze_numeric(
        self,
        points: list[AnalysisPoint],
        metadata: TagMetadata,
        request: AnalysisRequest,
        zero_policy: ZeroPolicy,
    ) -> TagAnalysisResult:
        stats = compute_numeric_stats(points, zero_policy)

        good_pts = [p for p in points if p.good]
        questionable_pts = [p for p in points if p.questionable]
        substituted_pts = [p for p in points if p.substituted]

        total = len(points) if points else 1
        good_pct = len(good_pts) / total * 100
        questionable_pct = len(questionable_pts) / total * 100
        substituted_pct = len(substituted_pts) / total * 100
        zero_pct = (stats.zero_count / total * 100) if total > 0 else 0

        verdict = assess_quality(
            good_pct, questionable_pct, substituted_pct, zero_pct, zero_policy
        )

        quality = QualityMetrics(
            good_pct=round(good_pct, 2),
            questionable_pct=round(questionable_pct, 2),
            substituted_pct=round(substituted_pct, 2),
            zero_pct=round(zero_pct, 2),
            verdict=verdict,
        )

        gaps_interp = detect_gaps_interpolated(points)
        gaps_rec = detect_gaps_recorded(points)
        spikes, spike_total = detect_spikes(points)

        warnings: list[str] = []
        if zero_policy == "suspicious" and stats.zero_count > 0:
            warnings.append(
                f"Politic suspicious: {stats.zero_count} zeros contabilizados."
            )

        return TagAnalysisResult(
            metadata=metadata,
            quality=quality,
            start_time=request.start_time,
            end_time=request.end_time,
            numeric=stats,
            gaps_interpolated=tuple(gaps_interp),
            gaps_recorded=tuple(gaps_rec),
            spikes=tuple(spikes),
            spike_total_count=spike_total,
            zero_policy_applied=zero_policy,
            warnings=tuple(warnings),
        )

    def _analyze_digital(
        self,
        data: CollectedData,
        request: AnalysisRequest,
        zero_policy: ZeroPolicy,
    ) -> TagAnalysisResult:
        metadata = data.metadata
        digital_states = data.digital_states

        # Resolver janela temporal (efetiva se houver truncamento)
        window_start = datetime.fromisoformat(request.start_time)
        effective_end_str = request.end_time
        if data.completeness is not None and data.completeness.effective_end_time:
            effective_end_str = data.completeness.effective_end_time
        window_end = datetime.fromisoformat(effective_end_str)

        # Reconstruir timeline digital
        digital_result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=data.digital_seed,
            recorded=data.recorded,
            possible_states=digital_states,
        )

        # Enriquecer com facts adicionais
        digital_result = enrich_digital_result(
            base=digital_result,
            recorded=data.recorded,
            seed=data.digital_seed,
            possible_states=digital_states,
            window_start=window_start,
            window_end=window_end,
        )

        # Derivar campos legados de digital_result
        durations = tuple(
            DigitalStateDuration(
                state=o.state_name,
                count=o.entries_count,
                percent=o.percentage_of_window,
                duration_seconds=o.duration_seconds,
            )
            for o in digital_result.occupancy
        )

        warnings: list[str] = list(digital_result.warnings)
        if zero_policy != "valid":
            warnings.append("Parâmetro zero_policy ignorado: tag é digital.")

        return TagAnalysisResult(
            metadata=metadata,
            quality=None,
            digital_analysis=digital_result,
            start_time=request.start_time,
            end_time=request.end_time,
            digital_durations=durations,
            digital_transitions=digital_result.transitions,
            zero_policy_applied=zero_policy,
            warnings=tuple(warnings),
            zero_policy_warning=(
                "Parâmetro zero_policy ignorado: tag é digital."
                if zero_policy != "valid"
                else None
            ),
        )


from domain.analysis.services.pi_data_collector import CollectedData  # noqa: E402
