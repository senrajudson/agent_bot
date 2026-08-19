from __future__ import annotations

from domain.analysis.models import (
    AnalysisError,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalStateDuration,
    DigitalStateOccupancy,
    DigitalStateRef,
    DigitalTransition,
    GapCandidate,
    MultiTagAnalysisResult,
    NumericStatistics,
    QualityMetrics,
    StateStatistic,
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
                quality=None,
                digital_analysis=DigitalAnalysisResult(
                    status=DigitalAnalysisStatus.COMPLETE,
                    possible_states=(DigitalStateRef(state_code=0, state_name="OFF"), DigitalStateRef(state_code=1, state_name="ON")),
                    initial_state=DigitalStateRef(state_code=0, state_name="OFF"),
                    final_state=DigitalStateRef(state_code=1, state_name="ON"),
                    occupancy=(
                        DigitalStateOccupancy(state_code=0, state_name="OFF", duration_seconds=1800, percentage_of_window=50.0, entries_count=1),
                        DigitalStateOccupancy(state_code=1, state_name="ON", duration_seconds=1800, percentage_of_window=50.0, entries_count=1),
                    ),
                    transitions=(DigitalTransition(from_state="OFF", to_state="ON", count=1, rate_per_hour=0.5),),
                    coverage=DigitalCoverageMetrics(
                        window_seconds=3600, known_seconds=3600, known_pct=100.0,
                        bad_seconds=0, bad_pct=0, null_seconds=0, null_pct=0,
                        unknown_seconds=0, unknown_pct=0, uncovered_seconds=0, uncovered_pct=0,
                        questionable_seconds=0, questionable_pct=0, substituted_seconds=0, substituted_pct=0,
                    ),
                    recorded_events_count=2,
                    valid_events_count=2,
                    state_statistics=(
                        StateStatistic(state_code=0, state_name="OFF", observed=True, entries_count=1, exits_count=1, segment_count=1, duration_seconds=1800, percentage_of_window=50.0, first_seen=None, last_seen=None, longest_segment_start=None, longest_segment_end=None, dwell_avg_seconds=1800.0, dwell_median_seconds=1800.0, dwell_min_seconds=1800.0, dwell_max_seconds=1800.0),
                        StateStatistic(state_code=1, state_name="ON", observed=True, entries_count=1, exits_count=0, segment_count=1, duration_seconds=1800, percentage_of_window=50.0, first_seen=None, last_seen=None, longest_segment_start=None, longest_segment_end=None, dwell_avg_seconds=1800.0, dwell_median_seconds=1800.0, dwell_min_seconds=1800.0, dwell_max_seconds=1800.0),
                    ),
                ),
                digital_durations=(DigitalStateDuration(state="OFF", count=1, percent=50.0, duration_seconds=1800), DigitalStateDuration(state="ON", count=1, percent=50.0, duration_seconds=1800)),
                digital_transitions=(DigitalTransition(from_state="OFF", to_state="ON", count=1, rate_per_hour=0.5),),
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
        assert "Estados" in names
        assert len(sheets) >= 10  # mixed has more sheets now

    def test_9_sheets_for_numeric_only(self) -> None:
        proj = XlsxAnalysisProjection()
        sheets = proj.project(_make_multi(have_digital=False))
        names = [s.name for s in sheets]
        assert "Estados" not in names
        assert "Digital_Set" not in names
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

    def test_xlsx_sheet_legacy_compatibility(self) -> None:
        from domain.analysis.services.xlsx_projection import XlsxSheet
        sheet = XlsxSheet(name="Test", columns=["a", "b"], rows=[[1, 2]])
        assert sheet.name == "Test"
        assert sheet.columns == ["a", "b"]
        assert sheet.rows == [[1, 2]]
        assert sheet.warnings == []
        assert sheet.is_presentation is False
        assert sheet.freeze_panes is None
        assert sheet.column_widths == {}
        assert sheet.merges == []
        assert sheet.cell_styles == {}
        assert sheet.is_active is False

