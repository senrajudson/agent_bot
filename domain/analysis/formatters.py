from __future__ import annotations

import re
from typing import Optional

from domain.analysis.models import (
    AbruptChangeCandidate,
    DigitalAnalysisStatus,
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

_STATUS_DESCRIPTIONS = {
    DigitalAnalysisStatus.COMPLETE: "Análise completa com transições entre estados conhecidos.",
    DigitalAnalysisStatus.NO_TRANSITIONS: "Estado conhecido durante toda a janela, sem transições registradas.",
    DigitalAnalysisStatus.PARTIAL_COVERAGE: "Parte da janela sem estado conhecido, normalmente pela ausência de seed no início.",
    DigitalAnalysisStatus.NO_DATA: "Nenhum seed nem evento utilizável para reconstruir a janela.",
    DigitalAnalysisStatus.INVALID_DIGITAL_VALUES: "Valores presentes, mas nenhum estado conhecido reconhecido.",
}


class InlineReportFormatter:
    def format(self, report: TagAnalysisResult) -> str:
        if report.digital_analysis is not None:
            return self._format_digital(report)
        return self._format_numeric(report)

    def _format_numeric(self, report: TagAnalysisResult) -> str:
        sections: list[str] = []
        sections.append(self._section_resumo_numeric(report))
        if report.numeric:
            sections.append(self._section_estatisticas(report.numeric, report.zero_policy_applied))
        sections.append(self._section_comportamento(report))
        sections.append(self._section_gaps(report.gaps_interpolated, report.gaps_recorded))
        if report.numeric:
            sections.append(self._section_spikes(report.spikes, report.spike_total_count))
        sections.append(self._section_qualidade(report.quality))
        sections.append(self._section_veredito(report.quality))
        return "\n\n".join(s for s in sections if s)

    def _format_digital(self, report: TagAnalysisResult) -> str:
        da = report.digital_analysis
        if da is None:
            return ""
        sections: list[str] = []
        sections.append(self._section_resumo_digital(report))
        sections.append(self._section_digital_status(da.status))
        sections.append(self._section_digital_summary(da, report))
        sections.append(self._section_digital_states(da))
        sections.append(self._section_digital_occupancy(da))
        sections.append(self._section_digital_transitions(da))
        sections.append(self._section_digital_coverage(da))
        sections.append(self._section_digital_operational())
        if report.warnings:
            sections.append(f"## Avisos\n{chr(10).join(report.warnings)}")
        return "\n\n".join(s for s in sections if s)

    def _section_resumo_numeric(self, report: TagAnalysisResult) -> str:
        m = report.metadata
        period = f"{report.start_time} → {report.end_time}" if report.start_time and report.end_time else "N/A"
        lines = [
            "## Resumo",
            f"Tag: {m.tag}",
            f"Descriptor: {m.descriptor or 'N/A'}",
            f"Eng Units: {m.engineering_units or 'N/A'}",
            f"Point Type: {m.point_type}",
            f"Período: {period}",
        ]
        return "\n".join(lines)

    def _section_resumo_digital(self, report: TagAnalysisResult) -> str:
        m = report.metadata
        period = f"{report.start_time} → {report.end_time}" if report.start_time and report.end_time else "N/A"
        ds = ""
        if report.digital_analysis:
            for ref in report.digital_analysis.possible_states[:1]:
                ds = m.digital_set or "N/A"
                break
        lines = [
            "## Resumo",
            f"Tag: {m.tag}",
            f"Descriptor: {m.descriptor or 'N/A'}",
            f"Eng Units: {m.engineering_units or 'N/A'}",
            f"Point Type: {m.point_type}",
            f"Digital Set: {m.digital_set or 'N/A'}",
            f"Período: {period}",
        ]
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
        if q is None:
            return ""
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

    def _section_digital_status(self, status: DigitalAnalysisStatus) -> str:
        desc = _STATUS_DESCRIPTIONS.get(status, "")
        return f"## Status Digital\n{status.value} — {desc}"

    def _section_digital_summary(self, da, report: TagAnalysisResult) -> str:
        lines = ["## Resumo Digital"]
        if da.initial_state:
            lines.append(f"Estado inicial: {da.initial_state.state_code} — {da.initial_state.state_name}")
        else:
            lines.append("Estado inicial: ausente")
        if da.final_state:
            lines.append(f"Estado final: {da.final_state.state_code} — {da.final_state.state_name}")
        else:
            lines.append("Estado final: ausente")
        lines.append(f"Eventos Recorded: {da.recorded_events_count}")
        lines.append(f"Eventos válidos: {da.valid_events_count}")
        lines.append(f"Transições: {len(da.transitions)}")
        return "\n".join(lines)

    def _section_digital_states(self, da) -> str:
        lines = ["## Estados Possíveis"]
        total = len(da.possible_states)
        observed = [o for o in da.occupancy if o.entries_count > 0]

        if total <= 10:
            for o in da.occupancy:
                lines.append(f"  {o.state_code} — {o.state_name}: {_r(o.percentage_of_window)}% ({_r(o.duration_seconds)}s) — {o.entries_count} entradas")
        else:
            for o in observed[:INLINE_MAX_STATES]:
                lines.append(f"  {o.state_code} — {o.state_name}: {_r(o.percentage_of_window)}% ({_r(o.duration_seconds)}s) — {o.entries_count} entradas")
            non_observed = total - len(observed)
            if non_observed > 0:
                lines.append(f"  ... {non_observed} estados não observados com 0% de ocupação")
        return "\n".join(lines)

    def _section_digital_occupancy(self, da) -> str:
        lines = ["## Ocupação Temporal"]
        for o in da.occupancy[:INLINE_MAX_STATES]:
            lines.append(f"  {o.state_code} — {o.state_name}: {_r(o.percentage_of_window)}% ({_r(o.duration_seconds)}s) — {o.entries_count} entradas")
        return "\n".join(lines)

    def _section_digital_transitions(self, da) -> str:
        lines = ["## Transições"]
        if da.transitions:
            lines.append(f"total: {len(da.transitions)}")
            for t in da.transitions[:INLINE_MAX_TRANSITIONS]:
                lines.append(f"  {t.from_state} → {t.to_state}: {t.count} (rate: {_r(t.rate_per_hour)}/h)")
        else:
            lines.append("Nenhuma transição foi observada durante a janela.")
        return "\n".join(lines)

    def _section_digital_coverage(self, da) -> str:
        c = da.coverage
        lines = [
            "## Integridade",
            f"Cobertura conhecida: {_r(c.known_pct)}%",
            f"Bad: {_r(c.bad_pct)}%",
            f"Null: {_r(c.null_pct)}%",
            f"Desconhecido: {_r(c.unknown_pct)}%",
            f"Sem cobertura: {_r(c.uncovered_pct)}%",
            f"Questionable (overlay): {_r(c.questionable_pct)}%",
            f"Substituted (overlay): {_r(c.substituted_pct)}%",
        ]
        return "\n".join(lines)

    def _section_digital_operational(self) -> str:
        return (
            "## Classificação Operacional\n"
            "Não aplicável. A análise digital é descritiva e não classifica "
            "os estados como bons, ruins, disponíveis ou indisponíveis."
        )

    def _section_qualidade(self, quality: Optional[QualityMetrics]) -> str:
        if quality is None:
            return ""
        return (
            "## Qualidade\n"
            f"good_pct: {_r(quality.good_pct)}%\n"
            f"questionable_pct: {_r(quality.questionable_pct)}%\n"
            f"substituted_pct: {_r(quality.substituted_pct)}%"
        )

    def _section_veredito(self, quality: Optional[QualityMetrics]) -> str:
        if quality is None:
            return ""
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
