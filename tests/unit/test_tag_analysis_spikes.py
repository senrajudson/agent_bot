from __future__ import annotations

from domain.analysis.models import AnalysisPoint
from domain.analysis.services._numeric import detect_spikes


class TestSpikes:
    def test_zscore_detection(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=1.0)
            for i in range(5)
        ] + [AnalysisPoint(timestamp="2026-01-01T00:25:00-03:00", value=100.0)]
        spikes, total = detect_spikes(pts)
        assert total >= 1

    def test_relative_detection(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=0.0)
            for i in range(5)
        ] + [AnalysisPoint(timestamp="2026-01-01T00:25:00-03:00", value=6.0)]
        spikes, total = detect_spikes(pts)
        assert total >= 1

    def test_both_detection(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=1.0)
            for i in range(5)
        ] + [AnalysisPoint(timestamp="2026-01-01T00:25:00-03:00", value=200.0)]
        spikes, total = detect_spikes(pts)
        assert total >= 1

    def test_std_zero_no_spikes(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=5.0)
            for i in range(10)
        ]
        spikes, total = detect_spikes(pts)
        assert total == 0

    def test_range_zero_no_spikes(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=0.0)
            for i in range(10)
        ]
        spikes, total = detect_spikes(pts)
        assert total == 0

    def test_top_5_by_magnitude(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i:02d}:00-03:00", value=float(i * 10))
            for i in range(10)
        ]
        spikes, total = detect_spikes(pts, top_n=5)
        assert len(spikes) <= 5
