from __future__ import annotations

import re
from typing import Optional

from domain.analysis.models import (
    AbruptChangeCandidate,
    DigitalStateDuration,
    DigitalTransition,
    GapCandidate,
    NumericStatistics,
    QualityMetrics,
    TagAnalysisResult,
    ZeroPolicy,
)
from domain.analysis.policies import (
    INLINE_MAX_GAPS,
    INLINE_MAX_SPIKES,
    INLINE_MAX_STATES,
    INLINE_MAX_TRANSITIONS,
    PROHIBITED_VERDICT_TERMS,
)


class InlineReportFormatter:
    def format(self, report: TagAnalysisResult) -> str:
        sections: list[str] = []

        sections.append(self._section_resumo(report))
        if report.numeric:
            sections.append(self._section_estatisticas(report.numeric, report.zero_policy_applied))
        sections.append(self._section_comportamento(report))
        sections.append(self._section_gaps(report.gaps_interpolated, report.gaps_recorded))
        if report.numeric:
            sections.append(self._section_spikes(report.spikes, report.spike_total_count))
        if report.metadata.point_type == "digital":
            sections.append(self._section_digital(report))
        sections.append(self._section_qualidade(report.quality))
        sections.append(self._section_veredito(report.quality))

        return "\n\n".join(s for s in sections if s)

    def _section_resumo(self, report: TagAnalysisResult) -> str:
        m = report.metadata
        lines = [
            "## Resumo",
            f"Tag: {m.tag}",
            f"Descriptor: {m.descriptor or 'N/A'}",
            f"Eng Units: {m.engineering_units or 'N/A'}",
            f"Point Type: {m.point_type}",
            f"Período: {report.quality.verdict}",
            f"Zero policy: {report.zero_policy_applied}",
        ]
        if report.warnings:
            lines.append(f"Avisos: {'; '.join(report.warnings)}")
        return "\n".join(lines)

    def _section_estatisticas(
        self, stats: NumericStatistics, zero_policy: ZeroPolicy
    ) -> str:
        lines = [
            "## Estatísticas",
            f"count: {stats.count}",
        ]
        if stats.min is not None:
            lines.append(f"min: {_r(stats.min)}")
        if stats.max is not None:
            lines.append(f"max: {_r(stats.max)}")
        if stats.mean is not None:
            lines.append(f"mean: {_r(stats.mean)}")
        if stats.median is not None:
            lines.append(f"median: {_r(stats.median)}")
        if stats.p01 is not None:
            lines.append(f"p01: {_r(stats.p01)}")
        if stats.p99 is not None:
            lines.append(f"p99: {_r(stats.p99)}")
        if stats.stddev_pop is not None:
            lines.append(f"stddev_pop: {_r(stats.stddev_pop)}")
        if stats.stddev_sample is not None:
            lines.append(f"stddev_sample: {_r(stats.stddev_sample)}")
        if stats.sum is not None:
            lines.append(f"sum: {_r(stats.sum)}")
        lines.append(f"zero_count: {stats.zero_count}")
        return "\n".join(lines)

    def _section_comportamento(self, report: TagAnalysisResult) -> str:
        q = report.quality
        lines = [
            "## Comportamento",
            f"good_pct: {_r(q.good_pct)}%",
            f"questionable_pct: {_r(q.questionable_pct)}%",
            f"substituted_pct: {_r(q.substituted_pct)}%",
            f"zero_pct: {_r(q.zero_pct)}% (policy: {report.zero_policy_applied})",
        ]
        return "\n".join(lines)

    def _section_gaps(
        self,
        gaps_interp: tuple[GapCandidate, ...],
        gaps_rec: tuple[GapCandidate, ...],
    ) -> str:
        lines = ["## Gaps"]

        lines.append("Interpolated:")
        lines.append(f"  total: {len(gaps_interp)}")
        if gaps_interp:
            max_g = max(g.duration_seconds for g in gaps_interp)
            total_s = sum(g.duration_seconds for g in gaps_interp)
            lines.append(f"  duration_total_seconds: {_r(total_s)}")
            lines.append(f"  max_seconds: {_r(max_g)}")
            for g in gaps_interp[:INLINE_MAX_GAPS]:
                lines.append(f"  - {g.start_ts} → {g.end_ts} ({_r(g.duration_seconds)}s)")

        lines.append("Recorded (descritivo):")
        lines.append(f"  total: {len(gaps_rec)}")
        if gaps_rec:
            max_g = max(g.duration_seconds for g in gaps_rec)
            total_s = sum(g.duration_seconds for g in gaps_rec)
            lines.append(f"  duration_total_seconds: {_r(total_s)}")
            lines.append(f"  max_seconds: {_r(max_g)}")
            for g in gaps_rec[:INLINE_MAX_GAPS]:
                lines.append(f"  - {g.start_ts} → {g.end_ts} ({_r(g.duration_seconds)}s)")

        return "\n".join(lines)

    def _section_spikes(
        self,
        spikes: tuple[AbruptChangeCandidate, ...],
        total: int,
    ) -> str:
        lines = [
            "## Mudanças Abruptas",
            f"total: {total}",
        ]
        for s in spikes[:INLINE_MAX_SPIKES]:
            lines.append(
                f"  - {s.timestamp}: {_r(s.previous_value)} → {_r(s.current_value)} "
                f"(Δ={_r(s.absolute_delta)}, rel={_r(s.relative_delta * 100)}%, basis={s.detection_basis})"
            )
        return "\n".join(lines)

    def _section_digital(self, report: TagAnalysisResult) -> str:
        lines = ["## Distribuição de Estados"]
        for d in report.digital_durations[:INLINE_MAX_STATES]:
            lines.append(
                f"  {d.state}: {d.count} ({_r(d.percent)}%) — {_r(d.duration_seconds)}s"
            )

        lines.append("")
        lines.append("## Transições")
        lines.append(f"total: {sum(t.count for t in report.digital_transitions)}")
        if report.digital_transitions:
            rate = report.digital_transitions[0].rate_per_hour
            lines.append(f"rate_per_hour: {_r(rate)}")
        for t in report.digital_transitions[:INLINE_MAX_TRANSITIONS]:
            lines.append(f"  {t.from_state} → {t.to_state}: {t.count}")

        return "\n".join(lines)

    def _section_qualidade(self, quality: QualityMetrics) -> str:
        return (
            "## Qualidade\n"
            f"good_pct: {_r(quality.good_pct)}%\n"
            f"questionable_pct: {_r(quality.questionable_pct)}%\n"
            f"substituted_pct: {_r(quality.substituted_pct)}%"
        )

    def _section_veredito(self, quality: QualityMetrics) -> str:
        verdict = quality.verdict
        _validate_no_prohibited_terms(verdict)
        return f"## Classificação da Qualidade dos Dados\n{verdict}"


def _r(v: float, n: int = 4) -> float:
    return round(v, n)


def _validate_no_prohibited_terms(verdict: str) -> None:
    lower = verdict.lower()
    for term in PROHIBITED_VERDICT_TERMS:
        if term in lower:
            raise ValueError(
                f"Termo proibido '{term}' encontrado no veredito: {verdict}"
            )
