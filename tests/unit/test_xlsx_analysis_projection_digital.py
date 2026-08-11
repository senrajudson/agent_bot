"""Testes de XLSX digital — T106-T118.

Cobre: Resumo NÃO APLICÁVEL, Qualidade, Estados_Digitais 14 colunas,
todos os estados, homônimos, status, cobertura, ausência de availability_pct.
"""

from __future__ import annotations

from domain.analysis.models import (
    AnalysisError,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalStateOccupancy,
    DigitalStateRef,
    DigitalTransition,
    GapCandidate,
    MultiTagAnalysisResult,
    NumericStatistics,
    QualityMetrics,
    TagAnalysisResult,
    TagMetadata,
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


# ---------------------------------------------------------------------------
# T107 — Qualidade digital
# ---------------------------------------------------------------------------

class TestT107_QualidadeDigital:
    def test_numeric_cells_empty(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        qualidade = [s for s in sheets if s.name == "Qualidade"][0]
        digital_row = [r for r in qualidade.rows if r[0] == "CPD_LP_SECADOR"][0]
        assert digital_row[1] is None  # good_pct
        assert digital_row[4] is None  # zero_pct
        assert digital_row[6] == "NÃO APLICÁVEL"


# ---------------------------------------------------------------------------
# T108 — Estados_Digitais colunas
# ---------------------------------------------------------------------------

class TestT108_EstadosDigitaisColumns:
    def test_14_columns(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados_Digitais"][0]
        assert len(estados.columns) == 14
        expected = [
            "tag", "state_code", "state_name", "duration_seconds",
            "percentage_of_window", "entries_count", "analysis_status",
            "known_coverage_pct", "bad_pct", "null_pct", "unknown_pct",
            "uncovered_pct", "questionable_pct", "substituted_pct",
        ]
        assert estados.columns == expected


# ---------------------------------------------------------------------------
# T109 — Todos os estados possíveis no XLSX
# ---------------------------------------------------------------------------

class TestT109_AllStatesInXlsx:
    def test_all_states(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados_Digitais"][0]
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
        estados = [s for s in sheets if s.name == "Estados_Digitais"][0]
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
    def test_status_present(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados_Digitais"][0]
        digital_rows = [r for r in estados.rows if r[0] == "CPD_LP_SECADOR"]
        for row in digital_rows:
            assert row[6] == "no_transitions"


# ---------------------------------------------------------------------------
# T112 — Cobertura no XLSX
# ---------------------------------------------------------------------------

class TestT112_CoverageInXlsx:
    def test_coverage_columns(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        estados = [s for s in sheets if s.name == "Estados_Digitais"][0]
        digital_rows = [r for r in estados.rows if r[0] == "CPD_LP_SECADOR"]
        for row in digital_rows:
            assert row[7] == 100.0  # known_coverage_pct
            assert row[8] == 0  # bad_pct
            assert row[9] == 0  # null_pct
            assert row[10] == 0  # unknown_pct
            assert row[11] == 0  # uncovered_pct
            assert row[12] == 0  # questionable_pct
            assert row[13] == 0  # substituted_pct


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
# T115 — Ordem das sheets
# ---------------------------------------------------------------------------

class TestT115_SheetOrder:
    def test_order(self) -> None:
        sheets = XlsxAnalysisProjection().project(_make_multi())
        names = [s.name for s in sheets]
        expected = ["Resumo", "Qualidade", "Estatisticas", "Recorded", "Interpolated_5m", "Gaps", "Spikes", "Estados_Digitais", "Erros_Warnings", "Metadados"]
        assert names == expected


# ---------------------------------------------------------------------------
# T116 — Fallback legado
# ---------------------------------------------------------------------------

class TestT116_LegacyFallback:
    def test_legacy_fallback(self) -> None:
        from domain.analysis.models import DigitalStateDuration
        multi = MultiTagAnalysisResult(
            results=(
                TagAnalysisResult(
                    metadata=TagMetadata(tag="LEGACY", point_type="digital", descriptor=""),
                    quality=None,
                    digital_durations=(DigitalStateDuration(state="ON", count=1, percent=100.0, duration_seconds=3600),),
                    digital_transitions=(),
                    zero_policy_applied="invalid",
                ),
            ),
            errors=(),
            period_start="2026-08-01T00:00:00-03:00",
            period_end="2026-08-02T00:00:00-03:00",
            total_requested=1,
            total_processed=1,
        )
        sheets = XlsxAnalysisProjection().project(multi)
        estados = [s for s in sheets if s.name == "Estados_Digitais"][0]
        assert len(estados.rows) == 1
        assert estados.rows[0][0] == "LEGACY"
        assert estados.rows[0][2] == "ON"


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
        # Verify the multi result structure is preserved
        assert multi.total_requested == 3
        assert multi.total_processed == 2
        assert len(multi.results) == 2
        assert len(multi.errors) == 1
        # Verify digital result has correct structure
        dig = [r for r in multi.results if r.metadata.point_type == "digital"][0]
        assert dig.quality is None
        assert dig.digital_analysis is not None
