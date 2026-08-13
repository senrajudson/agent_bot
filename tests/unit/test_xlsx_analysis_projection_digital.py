"""Testes de XLSX digital — T106-T118 (atualizados para novo schema).

Cobre: Resumo digital, Qualidade digital, Estados (18 colunas),
todos os estados, homônimos, status, cobertura, Recorded, availability.
"""

from __future__ import annotations

from domain.analysis.models import (
    AnalysisError,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalDiagnosticWarning,
    DigitalRecordedEvent,
    DigitalSetSnapshotEntry,
    DigitalStateOccupancy,
    DigitalStateRef,
    DigitalTransition,
    GapCandidate,
    MultiTagAnalysisResult,
    NumericStatistics,
    QualityMetrics,
    QualitySummary,
    SegmentKind,
    StateStatistic,
    TagAnalysisResult,
    TagMetadata,
    TimelineSegment,
)
from domain.analysis.services.xlsx_projection import XlsxAnalysisProjection


def _make_digital_result() -> TagAnalysisResult:
    return TagAnalysisResult(
        metadata=TagMetadata(tag="CPD_LP_SECADOR", point_type="digital", descriptor="Secador", digital_set="Estado_126"),
        quality=None,
        digital_analysis=DigitalAnalysisResult(
            status=DigitalAnalysisStatus.NO_TRANSITIONS,
            possible_states=(
                DigitalStateRef(state_code=0, state_name="DESLIGADO"),
                DigitalStateRef(state_code=1, state_name="VAZIO"),
                DigitalStateRef(state_code=2, state_name="LIGADO"),
                DigitalStateRef(state_code=3, state_name="VAZIO"),
                DigitalStateRef(state_code=4, state_name="FALHA"),
            ),
            initial_state=DigitalStateRef(state_code=0, state_name="DESLIGADO"),
            final_state=DigitalStateRef(state_code=0, state_name="DESLIGADO"),
            occupancy=(
                DigitalStateOccupancy(state_code=0, state_name="DESLIGADO", duration_seconds=604800, percentage_of_window=100.0, entries_count=1),
                DigitalStateOccupancy(state_code=1, state_name="VAZIO", duration_seconds=0, percentage_of_window=0, entries_count=0),
                DigitalStateOccupancy(state_code=2, state_name="LIGADO", duration_seconds=0, percentage_of_window=0, entries_count=0),
                DigitalStateOccupancy(state_code=3, state_name="VAZIO", duration_seconds=0, percentage_of_window=0, entries_count=0),
                DigitalStateOccupancy(state_code=4, state_name="FALHA", duration_seconds=0, percentage_of_window=0, entries_count=0),
            ),
            transitions=(),
            coverage=DigitalCoverageMetrics(
                window_seconds=604800, known_seconds=604800, known_pct=100.0,
                bad_seconds=0, bad_pct=0, null_seconds=0, null_pct=0,
                unknown_seconds=0, unknown_pct=0, uncovered_seconds=0, uncovered_pct=0,
                questionable_seconds=0, questionable_pct=0, substituted_seconds=0, substituted_pct=0,
            ),
            recorded_events_count=0,
            valid_events_count=0,
            quality_summary=QualitySummary(
                total_events=0, good_events=0, bad_events=0, questionable_events=0, substituted_events=0,
                known_duration=604800, bad_duration=0, unknown_duration=0, null_duration=0, uncovered_duration=0,
                questionable_duration=0, questionable_pct=0, substituted_duration=0, substituted_pct=0,
                bad_segment_count=0, unknown_segment_count=0,
                longest_bad_start=None, longest_bad_end=None, longest_bad_duration=0,
                longest_unknown_start=None, longest_unknown_end=None, longest_unknown_duration=0,
                first_bad_timestamp=None, last_bad_timestamp=None,
            ),
            state_statistics=(
                StateStatistic(state_code=0, state_name="DESLIGADO", observed=True, entries_count=1, exits_count=0, segment_count=1, duration_seconds=604800, percentage_of_window=100.0, first_seen=None, last_seen=None, longest_segment_start=None, longest_segment_end=None, dwell_avg_seconds=604800.0, dwell_median_seconds=604800.0, dwell_min_seconds=604800.0, dwell_max_seconds=604800.0),
                StateStatistic(state_code=1, state_name="VAZIO", observed=False, entries_count=0, exits_count=0, segment_count=0, duration_seconds=0, percentage_of_window=0, first_seen=None, last_seen=None, longest_segment_start=None, longest_segment_end=None, dwell_avg_seconds=None, dwell_median_seconds=None, dwell_min_seconds=None, dwell_max_seconds=None),
                StateStatistic(state_code=2, state_name="LIGADO", observed=False, entries_count=0, exits_count=0, segment_count=0, duration_seconds=0, percentage_of_window=0, first_seen=None, last_seen=None, longest_segment_start=None, longest_segment_end=None, dwell_avg_seconds=None, dwell_median_seconds=None, dwell_min_seconds=None, dwell_max_seconds=None),
                StateStatistic(state_code=3, state_name="VAZIO", observed=False, entries_count=0, exits_count=0, segment_count=0, duration_seconds=0, percentage_of_window=0, first_seen=None, last_seen=None, longest_segment_start=None, longest_segment_end=None, dwell_avg_seconds=None, dwell_median_seconds=None, dwell_min_seconds=None, dwell_max_seconds=None),
                StateStatistic(state_code=4, state_name="FALHA", observed=False, entries_count=0, exits_count=0, segment_count=0, duration_seconds=0, percentage_of_window=0, first_seen=None, last_seen=None, longest_segment_start=None, longest_segment_end=None, dwell_avg_seconds=None, dwell_median_seconds=None, dwell_min_seconds=None, dwell_max_seconds=None),
            ),
            digital_set_snapshot=(
                DigitalSetSnapshotEntry(state_code=0, state_name="DESLIGADO", state_description=None),
                DigitalSetSnapshotEntry(state_code=1, state_name="VAZIO", state_description=None),
                DigitalSetSnapshotEntry(state_code=2, state_name="LIGADO", state_description=None),
                DigitalSetSnapshotEntry(state_code=3, state_name="VAZIO", state_description=None),
                DigitalSetSnapshotEntry(state_code=4, state_name="FALHA", state_description=None),
            ),
            diagnostic_warnings=(),
        ),
        start_time="2026-08-01T00:00:00-03:00",
        end_time="2026-08-08T00:00:00-03:00",
    )


def _make_numeric_result() -> TagAnalysisResult:
    return TagAnalysisResult(
        metadata=TagMetadata(tag="LFI_NUM", point_type="numeric", descriptor="Num", engineering_units="Nm3/h"),
        quality=QualityMetrics(good_pct=99.0, questionable_pct=0.0, substituted_pct=0.0, zero_pct=1.0, verdict="DADOS_EXCELENTES"),
        numeric=NumericStatistics(count=100, min=1.0, max=100.0, mean=50.0, median=50.0),
        gaps_interpolated=(GapCandidate(method="interpolated", start_ts="a", end_ts="b", duration_seconds=900),),
        gaps_recorded=(),
        spikes=(),
        spike_total_count=0,
        zero_policy_applied="suspicious",
    )


def _make_multi() -> MultiTagAnalysisResult:
    return MultiTagAnalysisResult(
        results=(_make_numeric_result(), _make_digital_result()),
        errors=(AnalysisError(tag="FAIL", code="PI_TIMEOUT", message="timeout", retryable=True),),
        period_start="2026-08-01T00:00:00-03:00",
        period_end="2026-08-08T00:00:00-03:00",
        total_requested=3,
        total_processed=2,
    )


# ---------------------------------------------------------------------------
# T106 — Resumo digital
# ---------------------------------------------------------------------------

class TestT106_ResumoDigital:
    def test_nao_aplicavel(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        resumo = [s for s in sheets if s.name == "Resumo"][0]
        digital_row = [r for r in resumo.rows if r[0] == "CPD_LP_SECADOR"][0]
        assert digital_row[6] == "NÃO APLICÁVEL"

    def test_has_analysis_status(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        resumo = [s for s in sheets if s.name == "Resumo"][0]
        digital_row = [r for r in resumo.rows if r[0] == "CPD_LP_SECADOR"][0]
        # Mixed Resumo: analysis_status at index 9
        assert digital_row[9] == "no_transitions"
        assert "A tag permaneceu" in digital_row[10]

    def test_has_executive_diagnosis(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        resumo = [s for s in sheets if s.name == "Resumo"][0]
        digital_row = [r for r in resumo.rows if r[0] == "CPD_LP_SECADOR"][0]
        # diagnosis at index 18
        assert digital_row[18] != ""


# ---------------------------------------------------------------------------
# T107 — Qualidade digital
# ---------------------------------------------------------------------------

class TestT107_QualidadeDigital:
    def test_has_event_counts(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        qualidade = [s for s in sheets if s.name == "Qualidade"][0]
        digital_row = [r for r in qualidade.rows if r[0] == "CPD_LP_SECADOR"][0]
        assert digital_row[1] == "digital"
        # Mixed Qualidade: total_events at index 8
        assert digital_row[8] == 0  # total_events
        assert digital_row[9] == 0  # good_events

    def test_has_coverage(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        qualidade = [s for s in sheets if s.name == "Qualidade"][0]
        digital_row = [r for r in qualidade.rows if r[0] == "CPD_LP_SECADOR"][0]
        # Mixed Qualidade: known_duration_seconds at index 11
        assert digital_row[11] == 604800  # known_duration_seconds
        assert digital_row[12] == 0  # bad_duration_seconds


# ---------------------------------------------------------------------------
# T108 — Estados colunas
# ---------------------------------------------------------------------------

class TestT108_EstadosColumns:
    def test_18_columns(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados"][0]
        assert len(estados.columns) == 18
        expected = [
            "tag", "state_code", "state_name", "observed",
            "entries_count", "exits_count", "segment_count",
            "duration_seconds", "duration_human", "percentage_of_window",
            "dwell_avg_seconds", "dwell_median_seconds",
            "dwell_min_seconds", "dwell_max_seconds",
            "first_seen", "last_seen",
            "longest_segment_start", "longest_segment_end",
        ]
        assert estados.columns == expected


# ---------------------------------------------------------------------------
# T109 — Todos os estados possíveis no XLSX
# ---------------------------------------------------------------------------

class TestT109_AllStatesInXlsx:
    def test_all_states(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados"][0]
        codes = [r[1] for r in estados.rows if r[0] == "CPD_LP_SECADOR"]
        assert 0 in codes
        assert 1 in codes
        assert 2 in codes
        assert 3 in codes
        assert 4 in codes
        assert len([r for r in estados.rows if r[0] == "CPD_LP_SECADOR"]) == 5


# ---------------------------------------------------------------------------
# T110 — Estados homônimos no XLSX
# ---------------------------------------------------------------------------

class TestT110_HomonymousInXlsx:
    def test_distinct_codes(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados"][0]
        digital_rows = [r for r in estados.rows if r[0] == "CPD_LP_SECADOR"]
        codes = [r[1] for r in digital_rows]
        assert 1 in codes
        assert 3 in codes
        assert codes.count(1) == 1
        assert codes.count(3) == 1


# ---------------------------------------------------------------------------
# T111 — Status digital no XLSX
# ---------------------------------------------------------------------------

class TestT111_StatusInXlsx:
    def test_observed_present(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados"][0]
        digital_rows = [r for r in estados.rows if r[0] == "CPD_LP_SECADOR"]
        observed = [r[3] for r in digital_rows]
        assert True in observed
        assert False in observed


# ---------------------------------------------------------------------------
# T112 — Cobertura no XLSX
# ---------------------------------------------------------------------------

class TestT112_CoverageInXlsx:
    def test_duration_columns(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados"][0]
        digital_rows = [r for r in estados.rows if r[0] == "CPD_LP_SECADOR"]
        observed_row = [r for r in digital_rows if r[3] is True][0]
        assert observed_row[7] == 604800  # duration_seconds
        assert observed_row[9] == 100.0  # percentage_of_window


# ---------------------------------------------------------------------------
# T113 — Ausência de availability_pct
# ---------------------------------------------------------------------------

class TestT113_NoAvailability:
    def test_no_availability_column(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        for sheet in sheets:
            assert "availability_pct" not in sheet.columns


# ---------------------------------------------------------------------------
# T114 — Linhas numéricas inalteradas
# ---------------------------------------------------------------------------

class TestT114_NumericPreserved:
    def test_numeric_sheet(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estatisticas = [s for s in sheets if s.name == "Estatisticas"][0]
        num_row = [r for r in estatisticas.rows if r[0] == "LFI_NUM"][0]
        assert num_row[1] == 100  # count
        dig_row = [r for r in estatisticas.rows if r[0] == "CPD_LP_SECADOR"][0]
        assert dig_row[1] is None  # count empty for digital


# ---------------------------------------------------------------------------
# T115 — Ordem das sheets (mixed)
# ---------------------------------------------------------------------------

class TestT115_SheetOrder:
    def test_order(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        names = [s.name for s in sheets]
        # Mixed: Resumo, Qualidade, Recorded, Estatisticas, Interpolated_5m,
        # Gaps, Spikes, Estados, Digital_Set, Erros_Warnings, Metadados
        assert names[0] == "Resumo"
        assert names[1] == "Qualidade"
        assert "Estatisticas" in names
        assert "Recorded" in names
        assert "Interpolated_5m" in names
        assert "Gaps" in names
        assert "Spikes" in names
        assert "Estados" in names
        assert "Digital_Set" in names
        assert names[-2] == "Erros_Warnings"
        assert names[-1] == "Metadados"
        assert "Estados_Digitais" not in names


# ---------------------------------------------------------------------------
# T116 — Recorded digital populated
# ---------------------------------------------------------------------------

class TestT116_RecordedDigital:
    def test_recorded_has_rows(self) -> None:
        from domain.analysis.models import DigitalRecordedEvent
        multi = MultiTagAnalysisResult(
            results=(
                TagAnalysisResult(
                    metadata=TagMetadata(tag="TEST", point_type="digital", descriptor=""),
                    quality=None,
                    digital_analysis=DigitalAnalysisResult(
                        status=DigitalAnalysisStatus.COMPLETE,
                        possible_states=(DigitalStateRef(state_code=0, state_name="OFF"),),
                        initial_state=DigitalStateRef(state_code=0, state_name="OFF"),
                        final_state=DigitalStateRef(state_code=0, state_name="OFF"),
                        occupancy=(DigitalStateOccupancy(state_code=0, state_name="OFF", duration_seconds=3600, percentage_of_window=100.0, entries_count=1),),
                        transitions=(),
                        coverage=DigitalCoverageMetrics(
                            window_seconds=3600, known_seconds=3600, known_pct=100,
                            bad_seconds=0, bad_pct=0, null_seconds=0, null_pct=0,
                            unknown_seconds=0, unknown_pct=0, uncovered_seconds=0, uncovered_pct=0,
                            questionable_seconds=0, questionable_pct=0, substituted_seconds=0, substituted_pct=0,
                        ),
                        recorded_events_count=2,
                        valid_events_count=2,
                        classified_recorded_events=(
                            DigitalRecordedEvent(timestamp="2026-08-01T10:00:00", raw_value=0.0, resolved_code=0, resolved_state="OFF", classification=SegmentKind.KNOWN, good=True, questionable=False, substituted=False),
                            DigitalRecordedEvent(timestamp="2026-08-01T11:00:00", raw_value=0.0, resolved_code=0, resolved_state="OFF", classification=SegmentKind.KNOWN, good=True, questionable=False, substituted=False),
                        ),
                    ),
                    zero_policy_applied="invalid",
                ),
            ),
            period_start="2026-08-01T00:00:00", period_end="2026-08-02T00:00:00",
        )
        sheets = XlsxAnalysisProjection().project(multi)
        recorded = [s for s in sheets if s.name == "Recorded"][0]
        assert len(recorded.rows) == 2
        assert recorded.rows[0][0] == "TEST"
        assert recorded.rows[0][5] == "known"


# ---------------------------------------------------------------------------
# T117 — Partial success
# ---------------------------------------------------------------------------

class TestT117_PartialSuccess:
    def test_error_in_errors_sheet(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        erros = [s for s in sheets if s.name == "Erros_Warnings"][0]
        assert len(erros.rows) == 1
        assert erros.rows[0][1] == "PI_TIMEOUT"


# ---------------------------------------------------------------------------
# T118 — ArtifactManifest inalterado
# ---------------------------------------------------------------------------

class TestT118_ManifestUnchanged:
    def test_manifest_structure(self) -> None:
        multi = _make_multi()
        assert multi.total_requested == 3
        assert multi.total_processed == 2
        assert len(multi.results) == 2
        assert len(multi.errors) == 1
        dig = [r for r in multi.results if r.metadata.point_type == "digital"][0]
        assert dig.quality is None
        assert dig.digital_analysis is not None
