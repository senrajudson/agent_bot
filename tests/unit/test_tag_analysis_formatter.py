from __future__ import annotations

import re

from domain.analysis.formatters import InlineReportFormatter, _validate_no_prohibited_terms
from domain.analysis.models import (
    AbruptChangeCandidate,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalStateDuration,
    DigitalStateOccupancy,
    DigitalStateRef,
    DigitalTransition,
    GapCandidate,
    NumericStatistics,
    QualityMetrics,
    TagAnalysisResult,
    TagMetadata,
)


def _make_numeric_report() -> TagAnalysisResult:
    return TagAnalysisResult(
        metadata=TagMetadata(tag="LFI_TEST", point_type="numeric", descriptor="Test", engineering_units="Nm3/h"),
        quality=QualityMetrics(good_pct=99.5, questionable_pct=0.0, substituted_pct=0.0, zero_pct=2.0, verdict="DADOS_EXCELENTES"),
        numeric=NumericStatistics(count=100, min=1.0, max=100.0, mean=50.0, median=50.0, p01=1.0, p99=99.0, stddev_pop=28.8, stddev_sample=29.0, sum=5000.0, zero_count=2),
        gaps_interpolated=(
            GapCandidate(method="interpolated", start_ts="2026-01-01T00:00:00-03:00", end_ts="2026-01-01T01:00:00-03:00", duration_seconds=3600),
        ),
        gaps_recorded=(),
        spikes=(
            AbruptChangeCandidate(timestamp="2026-01-01T00:30:00-03:00", previous_value=50.0, current_value=100.0, absolute_delta=50.0, relative_delta=0.5, detection_basis="zscore"),
        ),
        spike_total_count=1,
        zero_policy_applied="suspicious",
        warnings=("Politic suspicious: 2 zeros contabilizados.",),
    )


def _make_digital_report() -> TagAnalysisResult:
    return TagAnalysisResult(
        metadata=TagMetadata(tag="ACI_VALVE", point_type="digital", descriptor="Valve"),
        quality=None,
        digital_analysis=DigitalAnalysisResult(
            status=DigitalAnalysisStatus.COMPLETE,
            possible_states=(
                DigitalStateRef(state_code=0, state_name="CLOSED"),
                DigitalStateRef(state_code=1, state_name="OPEN"),
            ),
            initial_state=DigitalStateRef(state_code=0, state_name="CLOSED"),
            final_state=DigitalStateRef(state_code=1, state_name="OPEN"),
            occupancy=(
                DigitalStateOccupancy(state_code=0, state_name="CLOSED", duration_seconds=21600, percentage_of_window=60.0, entries_count=1),
                DigitalStateOccupancy(state_code=1, state_name="OPEN", duration_seconds=14400, percentage_of_window=40.0, entries_count=1),
            ),
            transitions=(
                DigitalTransition(from_state="CLOSED", to_state="OPEN", count=3, rate_per_hour=0.5),
            ),
            coverage=DigitalCoverageMetrics(
                window_seconds=36000, known_seconds=36000, known_pct=100.0,
                bad_seconds=0, bad_pct=0, null_seconds=0, null_pct=0,
                unknown_seconds=0, unknown_pct=0, uncovered_seconds=0, uncovered_pct=0,
                questionable_seconds=0, questionable_pct=0, substituted_seconds=0, substituted_pct=0,
            ),
            recorded_events_count=3,
            valid_events_count=3,
        ),
        start_time="2026-01-01T00:00:00-03:00",
        end_time="2026-01-01T10:00:00-03:00",
        zero_policy_applied="suspicious",
        warnings=("Parâmetro zero_policy ignorado: tag é digital.",),
        zero_policy_warning="Parâmetro zero_policy ignorado: tag é digital.",
    )


class TestSectionOrder:
    def test_numeric_has_all_sections(self) -> None:
        formatter = InlineReportFormatter()
        text = formatter.format(_make_numeric_report())
        assert "## Resumo" in text
        assert "## Estatísticas" in text
        assert "## Comportamento" in text
        assert "## Gaps" in text
        assert "## Mudanças Abruptas" in text
        assert "## Qualidade" in text
        assert "## Classificação da Qualidade dos Dados" in text

    def test_digital_has_digital_sections(self) -> None:
        formatter = InlineReportFormatter()
        text = formatter.format(_make_digital_report())
        assert "## Status Digital" in text
        assert "## Ocupação Temporal" in text
        assert "## Transições" in text
        assert "CLOSED" in text
        assert "OPEN" in text
        assert "## Integridade" in text
        assert "## Classificação Operacional" in text


class TestProhibitedTerms:
    def test_no_prohibited_terms_in_output(self) -> None:
        formatter = InlineReportFormatter()
        text = formatter.format(_make_numeric_report())
        lower = text.lower()
        for term in ("processo", "equipamento", "operador", "normal", "anormal", "defeituoso"):
            assert term not in lower, f"Termo proibido '{term}' encontrado no output"

    def test_validate_no_prohibited_terms(self) -> None:
        _validate_no_prohibited_terms("DADOS_EXCELENTES")
        _validate_no_prohibited_terms("DADOS_SAUDÁVEIS")
        _validate_no_prohibited_terms("DADOS_ACEITÁVEIS")
        _validate_no_prohibited_terms("DADOS_DEGRADADOS")


class TestOutputSize:
    def test_output_under_8kb(self) -> None:
        formatter = InlineReportFormatter()
        text = formatter.format(_make_numeric_report())
        assert len(text.encode()) < 8192

    def test_no_raw_series(self) -> None:
        formatter = InlineReportFormatter()
        text = formatter.format(_make_numeric_report())
        assert "timestamp:" not in text.lower()
        assert "value:" not in text.lower()
