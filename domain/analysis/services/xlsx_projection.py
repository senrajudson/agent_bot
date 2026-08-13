from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domain.analysis.models import (
    DigitalAnalysisResult,
    MultiTagAnalysisResult,
    SegmentKind,
    TagAnalysisResult,
)
from domain.analysis.services._digital import format_duration


@dataclass(frozen=True)
class XlsxSheet:
    name: str
    columns: list[str]
    rows: list[list[Any]]
    warnings: list[str] = field(default_factory=list)


_STATUS_DESCRIPTIONS = {
    "complete": "Janela com cobertura válida e estados digitais reconhecidos.",
    "no_transitions": "A tag permaneceu no mesmo estado conhecido durante toda ou quase toda a janela.",
    "partial_coverage": "Parte da janela não pôde ser reconstruída.",
    "invalid_digital_values": "Não houve segmento KNOWN suficiente na janela.",
    "no_data": "Não foram encontrados dados suficientes para reconstruir a janela.",
}

_DIAGNOSIS_TEMPLATES = {
    "complete": "Janela com cobertura válida e estados digitais reconhecidos.",
    "no_transitions": "A tag permaneceu no mesmo estado conhecido durante toda ou quase toda a janela.",
    "partial_coverage": "Parte da janela não pôde ser reconstruída. Veja aba Linha_do_Tempo.",
    "invalid_digital_values": "Não houve segmento KNOWN suficiente na janela.",
    "no_data": "Não foram encontrados dados suficientes para reconstruir a janela.",
}

_WARNING_RECOMMENDATIONS = {
    "UNKNOWN_DIGITAL_VALUES": "Compare a aba Valores_Desconhecidos com a configuração atual do Digital Set. Valores fora do Digital Set podem indicar alteração histórica do set, escrita inesperada ou divergência de configuração.",
    "NO_KNOWN_DIGITAL_STATES": "Investigue Valores_Desconhecidos e Linha_do_Tempo.",
    "PARTIAL_TIMELINE_COVERAGE": "Verifique a disponibilidade de dados na aba Linha_do_Tempo.",
    "SEED_BAD_QUALITY": "O período inicial pode estar classificado como BAD por causa do seed.",
    "BAD_QUALITY_COVERAGE": "Investigue a integridade da coleta no PI nesta faixa.",
}


class XlsxAnalysisProjection:
    def project(self, multi: MultiTagAnalysisResult) -> list[XlsxSheet]:
        if self._is_all_numeric(multi):
            return self._project_numeric_only(multi)
        if self._is_all_digital(multi):
            return self._project_digital_only(multi)
        return self._project_mixed(multi)

    def _is_all_numeric(self, multi: MultiTagAnalysisResult) -> bool:
        return all(r.metadata.point_type == "numeric" for r in multi.results)

    def _is_all_digital(self, multi: MultiTagAnalysisResult) -> bool:
        return all(r.metadata.point_type == "digital" for r in multi.results)

    # ------------------------------------------------------------------
    # Numeric-only (preservado do baseline)
    # ------------------------------------------------------------------

    def _project_numeric_only(self, multi: MultiTagAnalysisResult) -> list[XlsxSheet]:
        return [
            self._resumo(multi),
            self._qualidade(multi),
            self._estatisticas(multi),
            self._recorded(multi),
            self._interpolated_5m(multi),
            self._gaps(multi),
            self._spikes(multi),
            self._erros_warnings(multi),
            self._metadados(multi),
        ]

    def _resumo(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "point_type", "descriptor", "eng_units", "period_start", "period_end", "quality_verdict"]
        rows = []
        for r in multi.results:
            verdict = "NÃO APLICÁVEL" if r.digital_analysis is not None else (r.quality.verdict if r.quality else "")
            rows.append([
                r.metadata.tag,
                r.metadata.point_type,
                r.metadata.descriptor,
                r.metadata.engineering_units or "",
                multi.period_start,
                multi.period_end,
                verdict,
            ])
        return XlsxSheet(name="Resumo", columns=columns, rows=rows)

    def _qualidade(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "good_pct", "questionable_pct", "substituted_pct", "zero_pct", "zero_policy", "verdict"]
        rows = []
        for r in multi.results:
            if r.digital_analysis is not None:
                rows.append([
                    r.metadata.tag, None, None, None, None,
                    r.zero_policy_applied, "NÃO APLICÁVEL",
                ])
            elif r.quality is not None:
                rows.append([
                    r.metadata.tag,
                    r.quality.good_pct,
                    r.quality.questionable_pct,
                    r.quality.substituted_pct,
                    r.quality.zero_pct,
                    r.zero_policy_applied,
                    r.quality.verdict,
                ])
            else:
                rows.append([r.metadata.tag, None, None, None, None, r.zero_policy_applied, ""])
        return XlsxSheet(name="Qualidade", columns=columns, rows=rows)

    def _estatisticas(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "count", "min", "max", "mean", "median", "p01", "p99", "stddev_pop", "stddev_sample", "sum", "zero_count"]
        rows = []
        for r in multi.results:
            if r.numeric:
                s = r.numeric
                rows.append([
                    r.metadata.tag, s.count, s.min, s.max, s.mean, s.median,
                    s.p01, s.p99, s.stddev_pop, s.stddev_sample, s.sum, s.zero_count,
                ])
            else:
                rows.append([r.metadata.tag, None, None, None, None, None, None, None, None, None, None, None])
        return XlsxSheet(name="Estatisticas", columns=columns, rows=rows)

    def _recorded(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "timestamp", "value", "good", "questionable", "substituted", "source"]
        rows = []
        return XlsxSheet(name="Recorded", columns=columns, rows=rows)

    def _interpolated_5m(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "timestamp", "value", "good", "questionable", "substituted"]
        rows = []
        has_digital = any(r.metadata.point_type == "digital" for r in multi.results)
        if has_digital and len(multi.results) > 0:
            rows.append(["N/A para tags digitais", "", "", "", "", ""])
        return XlsxSheet(name="Interpolated_5m", columns=columns, rows=rows)

    def _gaps(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "method", "start_ts", "end_ts", "duration_seconds"]
        rows = []
        for r in multi.results:
            for g in r.gaps_interpolated:
                rows.append([r.metadata.tag, "interpolated", g.start_ts, g.end_ts, g.duration_seconds])
            for g in r.gaps_recorded:
                rows.append([r.metadata.tag, "recorded", g.start_ts, g.end_ts, g.duration_seconds])
        return XlsxSheet(name="Gaps", columns=columns, rows=rows)

    def _spikes(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "timestamp", "prev_value", "cur_value", "abs_delta", "rel_delta", "basis"]
        rows = []
        for r in multi.results:
            for s in r.spikes:
                rows.append([
                    r.metadata.tag, s.timestamp, s.previous_value,
                    s.current_value, s.absolute_delta, s.relative_delta,
                    s.detection_basis,
                ])
        return XlsxSheet(name="Spikes", columns=columns, rows=rows)

    def _erros_warnings(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "code", "message", "retryable"]
        rows = []
        for e in multi.errors:
            rows.append([e.tag or "", e.code, e.message, e.retryable])
        return XlsxSheet(name="Erros_Warnings", columns=columns, rows=rows)

    def _metadados(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["key", "value"]
        rows = [
            ["tool_name", "generate_pi_tags_analysis_report"],
            ["period_start", multi.period_start],
            ["period_end", multi.period_end],
            ["total_requested", str(multi.total_requested)],
            ["total_processed", str(multi.total_processed)],
            ["schema_version", "1.0"],
        ]
        return XlsxSheet(name="Metadados", columns=columns, rows=rows)

    # ------------------------------------------------------------------
    # Digital-only
    # ------------------------------------------------------------------

    def _project_digital_only(self, multi: MultiTagAnalysisResult) -> list[XlsxSheet]:
        sheets: list[XlsxSheet] = []
        sheets.append(self._resumo_digital(multi))
        sheets.append(self._qualidade_digital(multi))
        sheets.append(self._recorded_digital(multi))

        # Condicionais — só quando há dados
        first_da = next(
            (r.digital_analysis for r in multi.results if r.digital_analysis is not None),
            None,
        )
        if first_da is not None:
            if first_da.state_statistics:
                sheets.append(self._estados(multi))
            if first_da.transition_statistics:
                sheets.append(self._transicoes(multi))
            if first_da.timeline_segments:
                sheets.append(self._linha_do_tempo(multi))
            if first_da.unknown_value_statistics:
                sheets.append(self._valores_desconhecidos(multi))
            if first_da.daily_summary:
                sheets.append(self._resumo_diario(multi))
            if first_da.digital_set_snapshot:
                sheets.append(self._digital_set(multi))

        sheets.append(self._erros_warnings(multi))
        sheets.append(self._metadados(multi))
        return sheets

    def _resumo_digital(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "description", "point_type", "digital_set",
            "window_start", "window_end", "window_duration_seconds",
            "analysis_status", "analysis_status_description",
            "recorded_event_count",
            "state_count_configured", "state_count_observed",
            "transition_count",
            "known_pct", "bad_pct", "unknown_pct", "null_pct", "uncovered_pct",
            "known_duration_seconds", "bad_duration_seconds",
            "unknown_duration_seconds", "null_duration_seconds", "uncovered_duration_seconds",
            "distinct_unknown_value_count",
            "longest_bad_duration_seconds", "longest_bad_start", "longest_bad_end",
            "longest_unknown_duration_seconds", "longest_unknown_start", "longest_unknown_end",
            "first_recorded_timestamp", "last_recorded_timestamp",
            "seed_found", "seed_timestamp", "seed_raw_value", "seed_good",
            "seed_classification", "seed_age_seconds_at_window_start",
            "executive_diagnosis", "investigative_recommendation",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                rows.append([r.metadata.tag] + [None] * (len(columns) - 1))
                continue
            cov = da.coverage
            qs = da.quality_summary
            si = da.seed_info
            status_val = da.status.value
            status_desc = _STATUS_DESCRIPTIONS.get(status_val, "")
            diagnosis = _DIAGNOSIS_TEMPLATES.get(status_val, "")

            # Recommendation do primeiro warning
            recommendation = ""
            for dw in da.diagnostic_warnings:
                rec = _WARNING_RECOMMENDATIONS.get(dw.code, "")
                if rec:
                    recommendation = rec
                    break

            first_rec = None
            last_rec = None
            if da.classified_recorded_events:
                first_rec = da.classified_recorded_events[0].timestamp
                last_rec = da.classified_recorded_events[-1].timestamp

            rows.append([
                r.metadata.tag,
                r.metadata.descriptor or "",
                r.metadata.point_type,
                r.metadata.digital_set or "",
                multi.period_start,
                multi.period_end,
                round(cov.window_seconds, 4),
                status_val,
                status_desc,
                da.recorded_events_count,
                len(da.possible_states),
                sum(1 for s in da.state_statistics if s.observed),
                sum(t.count for t in da.transition_statistics),
                cov.known_pct,
                cov.bad_pct,
                cov.unknown_pct,
                cov.null_pct,
                cov.uncovered_pct,
                cov.known_seconds,
                cov.bad_seconds,
                cov.unknown_seconds,
                cov.null_seconds,
                cov.uncovered_seconds,
                len(da.unknown_value_statistics),
                qs.longest_bad_duration if qs else 0,
                qs.longest_bad_start.isoformat() if qs and qs.longest_bad_start else None,
                qs.longest_bad_end.isoformat() if qs and qs.longest_bad_end else None,
                qs.longest_unknown_duration if qs else 0,
                qs.longest_unknown_start.isoformat() if qs and qs.longest_unknown_start else None,
                qs.longest_unknown_end.isoformat() if qs and qs.longest_unknown_end else None,
                first_rec,
                last_rec,
                si.found if si else False,
                si.timestamp if si else None,
                si.raw_value if si else None,
                si.good if si else None,
                si.classification.value if si and si.classification else None,
                si.age_seconds_at_window_start if si else None,
                diagnosis,
                recommendation,
            ])
        return XlsxSheet(name="Resumo", columns=columns, rows=rows)

    def _qualidade_digital(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "point_type",
            "total_events", "good_events", "bad_events",
            "questionable_events", "substituted_events",
            "known_duration_seconds", "bad_duration_seconds",
            "unknown_duration_seconds", "null_duration_seconds", "uncovered_duration_seconds",
            "known_pct", "bad_pct", "unknown_pct", "null_pct", "uncovered_pct",
            "questionable_duration_seconds", "questionable_pct",
            "substituted_duration_seconds", "substituted_pct",
            "bad_segment_count", "longest_bad_duration_seconds",
            "longest_bad_start", "longest_bad_end",
            "first_bad_timestamp", "last_bad_timestamp",
            "unknown_segment_count", "longest_unknown_duration_seconds",
            "longest_unknown_start", "longest_unknown_end",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                rows.append([r.metadata.tag, r.metadata.point_type] + [None] * (len(columns) - 2))
                continue
            cov = da.coverage
            qs = da.quality_summary
            rows.append([
                r.metadata.tag,
                r.metadata.point_type,
                qs.total_events if qs else 0,
                qs.good_events if qs else 0,
                qs.bad_events if qs else 0,
                qs.questionable_events if qs else 0,
                qs.substituted_events if qs else 0,
                cov.known_seconds,
                cov.bad_seconds,
                cov.unknown_seconds,
                cov.null_seconds,
                cov.uncovered_seconds,
                cov.known_pct,
                cov.bad_pct,
                cov.unknown_pct,
                cov.null_pct,
                cov.uncovered_pct,
                cov.questionable_seconds,
                cov.questionable_pct,
                cov.substituted_seconds,
                cov.substituted_pct,
                qs.bad_segment_count if qs else 0,
                qs.longest_bad_duration if qs else 0,
                qs.longest_bad_start.isoformat() if qs and qs.longest_bad_start else None,
                qs.longest_bad_end.isoformat() if qs and qs.longest_bad_end else None,
                qs.first_bad_timestamp if qs else None,
                qs.last_bad_timestamp if qs else None,
                qs.unknown_segment_count if qs else 0,
                qs.longest_unknown_duration if qs else 0,
                qs.longest_unknown_start.isoformat() if qs and qs.longest_unknown_start else None,
                qs.longest_unknown_end.isoformat() if qs and qs.longest_unknown_end else None,
            ])
        return XlsxSheet(name="Qualidade", columns=columns, rows=rows)

    def _recorded_digital(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "timestamp", "raw_value",
            "resolved_code", "resolved_state",
            "classification", "good", "questionable", "substituted",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                continue
            for ev in da.classified_recorded_events:
                rows.append([
                    r.metadata.tag,
                    ev.timestamp,
                    ev.raw_value,
                    ev.resolved_code,
                    ev.resolved_state,
                    ev.classification.value,
                    ev.good,
                    ev.questionable,
                    ev.substituted,
                ])
        return XlsxSheet(name="Recorded", columns=columns, rows=rows)

    def _estados(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "state_code", "state_name", "observed",
            "entries_count", "exits_count", "segment_count",
            "duration_seconds", "duration_human", "percentage_of_window",
            "dwell_avg_seconds", "dwell_median_seconds",
            "dwell_min_seconds", "dwell_max_seconds",
            "first_seen", "last_seen",
            "longest_segment_start", "longest_segment_end",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                continue
            for ss in da.state_statistics:
                rows.append([
                    r.metadata.tag,
                    ss.state_code,
                    ss.state_name,
                    ss.observed,
                    ss.entries_count,
                    ss.exits_count,
                    ss.segment_count,
                    ss.duration_seconds,
                    format_duration(ss.duration_seconds) if ss.duration_seconds > 0 else "00s",
                    ss.percentage_of_window,
                    ss.dwell_avg_seconds,
                    ss.dwell_median_seconds,
                    ss.dwell_min_seconds,
                    ss.dwell_max_seconds,
                    ss.first_seen.isoformat() if ss.first_seen else None,
                    ss.last_seen.isoformat() if ss.last_seen else None,
                    ss.longest_segment_start.isoformat() if ss.longest_segment_start else None,
                    ss.longest_segment_end.isoformat() if ss.longest_segment_end else None,
                ])
        return XlsxSheet(name="Estados", columns=columns, rows=rows)

    def _transicoes(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "from_kind", "from_code", "from_name",
            "to_kind", "to_code", "to_name",
            "transition_count", "percentage_of_transitions",
            "first_transition", "last_transition",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                continue
            for ts in da.transition_statistics:
                rows.append([
                    r.metadata.tag,
                    ts.from_kind.value if ts.from_kind else None,
                    ts.from_code,
                    ts.from_name,
                    ts.to_kind.value if ts.to_kind else None,
                    ts.to_code,
                    ts.to_name,
                    ts.count,
                    ts.percentage_of_transitions,
                    ts.first_transition.isoformat() if ts.first_transition else None,
                    ts.last_transition.isoformat() if ts.last_transition else None,
                ])
        return XlsxSheet(name="Transicoes", columns=columns, rows=rows)

    def _linha_do_tempo(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "segment_start", "segment_end",
            "duration_seconds", "duration_human",
            "raw_value", "state_code", "state_name",
            "segment_kind", "good", "questionable", "substituted", "source",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                continue
            for seg in da.timeline_segments:
                rows.append([
                    r.metadata.tag,
                    seg.start.isoformat() if hasattr(seg.start, 'isoformat') else str(seg.start),
                    seg.end.isoformat() if hasattr(seg.end, 'isoformat') else str(seg.end),
                    seg.duration_seconds,
                    format_duration(seg.duration_seconds),
                    seg.raw_value,
                    seg.state_code,
                    seg.state_name,
                    seg.kind.value,
                    seg.good,
                    seg.questionable,
                    seg.substituted,
                    seg.source.value if seg.source else None,
                ])
        return XlsxSheet(name="Linha_do_Tempo", columns=columns, rows=rows)

    def _valores_desconhecidos(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "raw_value", "occurrences", "segment_count",
            "duration_seconds", "duration_human", "percentage_of_window",
            "first_seen", "last_seen", "sample_timestamp",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                continue
            for uv in da.unknown_value_statistics:
                rows.append([
                    r.metadata.tag,
                    uv.raw_value,
                    uv.occurrences,
                    uv.segment_count,
                    uv.duration_seconds,
                    format_duration(uv.duration_seconds),
                    uv.percentage_of_window,
                    uv.first_seen.isoformat() if uv.first_seen else None,
                    uv.last_seen.isoformat() if uv.last_seen else None,
                    uv.sample_timestamp,
                ])
        return XlsxSheet(name="Valores_Desconhecidos", columns=columns, rows=rows)

    def _resumo_diario(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "date",
            "known_pct", "bad_pct", "unknown_pct", "null_pct", "uncovered_pct",
            "transition_count",
            "dominant_state_code", "dominant_state_name", "dominant_state_pct",
            "distinct_states_observed", "distinct_unknown_values",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                continue
            for db in da.daily_summary:
                rows.append([
                    r.metadata.tag,
                    db.date,
                    db.known_pct,
                    db.bad_pct,
                    db.unknown_pct,
                    db.null_pct,
                    db.uncovered_pct,
                    db.transition_count,
                    db.dominant_state_code,
                    db.dominant_state_name,
                    db.dominant_state_pct,
                    db.distinct_states_observed,
                    db.distinct_unknown_values,
                ])
        return XlsxSheet(name="Resumo_Diario", columns=columns, rows=rows)

    def _digital_set(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "digital_set_name", "state_code", "state_name", "state_description"]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is None:
                continue
            for dse in da.digital_set_snapshot:
                rows.append([
                    r.metadata.tag,
                    r.metadata.digital_set or "",
                    dse.state_code,
                    dse.state_name,
                    dse.state_description,
                ])
        return XlsxSheet(name="Digital_Set", columns=columns, rows=rows)

    # ------------------------------------------------------------------
    # Mixed
    # ------------------------------------------------------------------

    def _project_mixed(self, multi: MultiTagAnalysisResult) -> list[XlsxSheet]:
        sheets: list[XlsxSheet] = []
        sheets.append(self._resumo_mixed(multi))
        sheets.append(self._qualidade_mixed(multi))
        sheets.append(self._recorded_mixed(multi))
        sheets.append(self._estatisticas(multi))
        sheets.append(self._interpolated_5m(multi))
        sheets.append(self._gaps(multi))
        sheets.append(self._spikes(multi))

        # Digital-specific sheets (only rows from digital tags)
        has_digital_states = any(
            r.digital_analysis is not None and r.digital_analysis.state_statistics
            for r in multi.results
        )
        has_digital_trans = any(
            r.digital_analysis is not None and r.digital_analysis.transition_statistics
            for r in multi.results
        )
        has_digital_timeline = any(
            r.digital_analysis is not None and r.digital_analysis.timeline_segments
            for r in multi.results
        )
        has_digital_unknown = any(
            r.digital_analysis is not None and r.digital_analysis.unknown_value_statistics
            for r in multi.results
        )
        has_digital_daily = any(
            r.digital_analysis is not None and r.digital_analysis.daily_summary
            for r in multi.results
        )
        has_digital_set = any(
            r.digital_analysis is not None and r.digital_analysis.digital_set_snapshot
            for r in multi.results
        )

        if has_digital_states:
            sheets.append(self._estados(multi))
        if has_digital_trans:
            sheets.append(self._transicoes(multi))
        if has_digital_timeline:
            sheets.append(self._linha_do_tempo(multi))
        if has_digital_unknown:
            sheets.append(self._valores_desconhecidos(multi))
        if has_digital_daily:
            sheets.append(self._resumo_diario(multi))
        if has_digital_set:
            sheets.append(self._digital_set(multi))

        sheets.append(self._erros_warnings(multi))
        sheets.append(self._metadados(multi))
        return sheets

    def _resumo_mixed(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        # Superset of resumo + resumo_digital columns
        columns = [
            "tag", "point_type", "descriptor", "eng_units",
            "period_start", "period_end", "quality_verdict",
            "digital_set", "window_duration_seconds",
            "analysis_status", "analysis_status_description",
            "recorded_event_count",
            "known_pct", "bad_pct", "unknown_pct", "null_pct", "uncovered_pct",
            "distinct_unknown_value_count",
            "executive_diagnosis", "investigative_recommendation",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is not None:
                cov = da.coverage
                diagnosis = _DIAGNOSIS_TEMPLATES.get(da.status.value, "")
                recommendation = ""
                for dw in da.diagnostic_warnings:
                    rec = _WARNING_RECOMMENDATIONS.get(dw.code, "")
                    if rec:
                        recommendation = rec
                        break
                rows.append([
                    r.metadata.tag,
                    r.metadata.point_type,
                    r.metadata.descriptor or "",
                    r.metadata.engineering_units or "",
                    multi.period_start,
                    multi.period_end,
                    "NÃO APLICÁVEL",
                    r.metadata.digital_set or "",
                    round(cov.window_seconds, 4),
                    da.status.value,
                    _STATUS_DESCRIPTIONS.get(da.status.value, ""),
                    da.recorded_events_count,
                    cov.known_pct,
                    cov.bad_pct,
                    cov.unknown_pct,
                    cov.null_pct,
                    cov.uncovered_pct,
                    len(da.unknown_value_statistics),
                    diagnosis,
                    recommendation,
                ])
            else:
                verdict = r.quality.verdict if r.quality else ""
                rows.append([
                    r.metadata.tag,
                    r.metadata.point_type,
                    r.metadata.descriptor or "",
                    r.metadata.engineering_units or "",
                    multi.period_start,
                    multi.period_end,
                    verdict,
                    None, None, None, None, None, None,
                    None, None, None, None, None, None, None, None,
                ])
        return XlsxSheet(name="Resumo", columns=columns, rows=rows)

    def _qualidade_mixed(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "point_type",
            "good_pct", "questionable_pct", "substituted_pct",
            "zero_pct", "zero_policy", "verdict",
            "total_events", "good_events", "bad_events",
            "known_duration_seconds", "bad_duration_seconds",
            "unknown_duration_seconds", "null_duration_seconds", "uncovered_duration_seconds",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is not None:
                cov = da.coverage
                qs = da.quality_summary
                rows.append([
                    r.metadata.tag,
                    r.metadata.point_type,
                    None, None, None, None, r.zero_policy_applied, "NÃO APLICÁVEL",
                    qs.total_events if qs else 0,
                    qs.good_events if qs else 0,
                    qs.bad_events if qs else 0,
                    cov.known_seconds,
                    cov.bad_seconds,
                    cov.unknown_seconds,
                    cov.null_seconds,
                    cov.uncovered_seconds,
                ])
            elif r.quality is not None:
                rows.append([
                    r.metadata.tag,
                    r.metadata.point_type,
                    r.quality.good_pct,
                    r.quality.questionable_pct,
                    r.quality.substituted_pct,
                    r.quality.zero_pct,
                    r.zero_policy_applied,
                    r.quality.verdict,
                    None, None, None, None, None, None, None, None,
                ])
            else:
                rows.append([
                    r.metadata.tag, r.metadata.point_type,
                    None, None, None, None, r.zero_policy_applied, "",
                    None, None, None, None, None, None, None, None,
                ])
        return XlsxSheet(name="Qualidade", columns=columns, rows=rows)

    def _recorded_mixed(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = [
            "tag", "point_type",
            "timestamp", "value", "good", "questionable", "substituted",
            "raw_value", "resolved_code", "resolved_state", "classification",
        ]
        rows = []
        for r in multi.results:
            da = r.digital_analysis
            if da is not None:
                for ev in da.classified_recorded_events:
                    rows.append([
                        r.metadata.tag, r.metadata.point_type,
                        ev.timestamp, None, ev.good, ev.questionable, ev.substituted,
                        ev.raw_value, ev.resolved_code, ev.resolved_state,
                        ev.classification.value,
                    ])
        return XlsxSheet(name="Recorded", columns=columns, rows=rows)
