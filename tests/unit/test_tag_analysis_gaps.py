from __future__ import annotations

from domain.analysis.models import AnalysisPoint
from domain.analysis.services._numeric import detect_gaps_interpolated, detect_gaps_recorded


class TestGapsInterpolated:
    def test_gap_detected_3_plus_slots(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=2.0),
            AnalysisPoint(timestamp="2026-01-01T00:25:00-03:00", value=3.0),
        ]
        gaps = detect_gaps_interpolated(pts)
        assert len(gaps) == 1
        assert gaps[0].duration_seconds > 900

    def test_no_gaps_regular_series(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=float(i))
            for i in range(10)
        ]
        gaps = detect_gaps_interpolated(pts)
        assert len(gaps) == 0

    def test_top_5_gaps(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=2.0),
            AnalysisPoint(timestamp="2026-01-01T01:00:00-03:00", value=3.0),
            AnalysisPoint(timestamp="2026-01-01T01:05:00-03:00", value=4.0),
            AnalysisPoint(timestamp="2026-01-01T03:00:00-03:00", value=5.0),
        ]
        gaps = detect_gaps_interpolated(pts)
        assert len(gaps) <= 5

    def test_gap_count_separated(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=2.0),
            AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=3.0),
            AnalysisPoint(timestamp="2026-01-01T02:05:00-03:00", value=4.0),
            AnalysisPoint(timestamp="2026-01-01T06:00:00-03:00", value=5.0),
        ]
        gaps = detect_gaps_interpolated(pts)
        assert len(gaps) == 2
        assert all(g.method == "interpolated" for g in gaps)


class TestGapsRecorded:
    def test_gap_detected_descritivo(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i:02d}:00-03:00", value=float(i))
            for i in range(10)
        ] + [AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=100.0)]
        gaps = detect_gaps_recorded(pts)
        assert len(gaps) == 1
        assert gaps[0].method == "recorded"

    def test_no_gaps_for_regular(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i:02d}:00-03:00", value=float(i))
            for i in range(10)
        ]
        gaps = detect_gaps_recorded(pts)
        assert len(gaps) == 0
