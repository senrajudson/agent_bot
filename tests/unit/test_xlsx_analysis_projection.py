from __future__ import annotations

from domain.analysis.models import (
    AnalysisError,
    DigitalStateDuration,
    DigitalTransition,
    GapCandidate,
    MultiTagAnalysisResult,
    NumericStatistics,
    QualityMetrics,
    TagAnalysisResult,
    TagMetadata,
)
from domain.analysis.services.xlsx_projection import XlsxAnalysisProjection


def _make_multi(have_digital: bool = False) -> MultiTagAnalysisResult:
    results = [
        TagAnalysisResult(
            metadata=TagMetadata(tag="LFI_NUM", point_type="numeric", descriptor="Num", engineering_units="Nm3/h"),
            quality=QualityMetrics(good_pct=99.0, questionable_pct=0.0, substituted_pct=0.0, zero_pct=1.0, verdict="DADOS_EXCELENTES"),
            numeric=NumericStatistics(count=100, min=1.0, max=100.0, mean=50.0, median=50.0),
            gaps_interpolated=(GapCandidate(method="interpolated", start_ts="a", end_ts="b", duration_seconds=900),),
            gaps_recorded=(),
            spikes=(),
            spike_total_count=0,
            zero_policy_applied="suspicious",
        ),
    ]
    if have_digital:
        results.append(
            TagAnalysisResult(
                metadata=TagMetadata(tag="ACI_DIG", point_type="digital", descriptor="Dig"),
                quality=QualityMetrics(good_pct=100.0, questionable_pct=0.0, substituted_pct=0.0, zero_pct=0.0, verdict="DADOS_EXCELENTES"),
                digital_durations=(DigitalStateDuration(state="ON", count=1, percent=100.0, duration_seconds=3600),),
                digital_transitions=(),
                zero_policy_applied="invalid",
            )
        )

    return MultiTagAnalysisResult(
        results=tuple(results),
        errors=(AnalysisError(tag="FAIL", code="PI_TIMEOUT", message="timeout", retryable=True),),
        period_start="2026-01-01T00:00:00-03:00",
        period_end="2026-01-02T00:00:00-03:00",
        total_requested=3,
        total_processed=2,
    )


class TestProjection:
    def test_10_sheets_for_mixed(self) -> None:
        proj = XlsxAnalysisProjection()
        sheets = proj.project(_make_multi(have_digital=True))
        names = [s.name for s in sheets]
        assert "Estados_Digitais" in names
        assert len(sheets) == 10

    def test_9_sheets_for_numeric_only(self) -> None:
        proj = XlsxAnalysisProjection()
        sheets = proj.project(_make_multi(have_digital=False))
        names = [s.name for s in sheets]
        assert "Estados_Digitais" not in names
        assert len(sheets) == 9

    def test_columns_per_sheet(self) -> None:
        proj = XlsxAnalysisProjection()
        sheets = proj.project(_make_multi(have_digital=True))
        for s in sheets:
            assert len(s.columns) > 0
            assert all(isinstance(c, str) for c in s.columns)

    def test_interpolated_5m_always_present(self) -> None:
        proj = XlsxAnalysisProjection()
        sheets = proj.project(_make_multi(have_digital=True))
        names = [s.name for s in sheets]
        assert "Interpolated_5m" in names

    def test_metadata_sheet(self) -> None:
        proj = XlsxAnalysisProjection()
        sheets = proj.project(_make_multi(have_digital=False))
        meta = [s for s in sheets if s.name == "Metadados"]
        assert len(meta) == 1
        assert len(meta[0].rows) > 0

    def test_errors_warnings(self) -> None:
        proj = XlsxAnalysisProjection()
        sheets = proj.project(_make_multi(have_digital=False))
        errs = [s for s in sheets if s.name == "Erros_Warnings"]
        assert len(errs) == 1
        assert len(errs[0].rows) == 1
        assert errs[0].rows[0][1] == "PI_TIMEOUT"
