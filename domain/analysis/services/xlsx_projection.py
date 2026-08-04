from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domain.analysis.models import MultiTagAnalysisResult, TagAnalysisResult


@dataclass(frozen=True)
class XlsxSheet:
    name: str
    columns: list[str]
    rows: list[list[Any]]
    warnings: list[str] = field(default_factory=list)


class XlsxAnalysisProjection:
    def project(self, multi: MultiTagAnalysisResult) -> list[XlsxSheet]:
        sheets: list[XlsxSheet] = []
        sheets.append(self._resumo(multi))
        sheets.append(self._qualidade(multi))
        sheets.append(self._estatisticas(multi))
        sheets.append(self._recorded(multi))
        sheets.append(self._interpolated_5m(multi))
        sheets.append(self._gaps(multi))
        sheets.append(self._spikes(multi))
        if any(r.metadata.point_type == "digital" for r in multi.results):
            sheets.append(self._estados_digitais(multi))
        sheets.append(self._erros_warnings(multi))
        sheets.append(self._metadados(multi))
        return sheets

    def _resumo(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "point_type", "descriptor", "eng_units", "period_start", "period_end", "quality_verdict"]
        rows = []
        for r in multi.results:
            rows.append([
                r.metadata.tag,
                r.metadata.point_type,
                r.metadata.descriptor,
                r.metadata.engineering_units or "",
                multi.period_start,
                multi.period_end,
                r.quality.verdict,
            ])
        return XlsxSheet(name="Resumo", columns=columns, rows=rows)

    def _qualidade(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "good_pct", "questionable_pct", "substituted_pct", "zero_pct", "zero_policy", "verdict"]
        rows = []
        for r in multi.results:
            rows.append([
                r.metadata.tag,
                r.quality.good_pct,
                r.quality.questionable_pct,
                r.quality.substituted_pct,
                r.quality.zero_pct,
                r.zero_policy_applied,
                r.quality.verdict,
            ])
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
                rows.append([r.metadata.tag, "", "", "", "", "", "", "", "", "", "", ""])
        return XlsxSheet(name="Estatisticas", columns=columns, rows=rows)

    def _recorded(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "timestamp", "value", "good", "questionable", "substituted", "source"]
        rows = []
        # Recorded points are not stored in TagAnalysisResult directly
        # This sheet is a placeholder for future expansion
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

    def _estados_digitais(self, multi: MultiTagAnalysisResult) -> XlsxSheet:
        columns = ["tag", "state", "count", "percent", "duration_seconds"]
        rows = []
        for r in multi.results:
            if r.metadata.point_type == "digital":
                for d in r.digital_durations:
                    rows.append([r.metadata.tag, d.state, d.count, d.percent, d.duration_seconds])
        return XlsxSheet(name="Estados_Digitais", columns=columns, rows=rows)

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
