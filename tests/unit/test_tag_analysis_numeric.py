from __future__ import annotations

import pytest

from domain.analysis.models import AnalysisPoint
from domain.analysis.services._numeric import (
    compute_numeric_stats,
    detect_gaps_interpolated,
    detect_gaps_recorded,
    detect_spikes,
)


def _pts(*values: float | None, base_ts: str = "2026-01-01T00:00:00-03:00") -> list[AnalysisPoint]:
    from datetime import timedelta

    result = []
    ts = base_ts
    for i, v in enumerate(values):
        result.append(AnalysisPoint(timestamp=ts, value=v))
        # advance 5 min
        from datetime import datetime, timezone

        dt = datetime(2026, 1, 1, 0, i * 5, tzinfo=timezone(timedelta(hours=-3)))
        ts = dt.isoformat()
    return result


class TestComputeNumericStats:
    def test_basic_metrics(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=20.0),
            AnalysisPoint(timestamp="2026-01-01T00:10:00-03:00", value=30.0),
        ]
        stats = compute_numeric_stats(pts, "valid")
        assert stats.count == 3
        assert stats.min == 10.0
        assert stats.max == 30.0
        assert stats.mean == 20.0
        assert stats.sum == 60.0

    def test_empty_series(self) -> None:
        stats = compute_numeric_stats([], "valid")
        assert stats.count == 0
        assert stats.min is None
        assert stats.max is None

    def test_constant_series(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=5.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=5.0),
            AnalysisPoint(timestamp="2026-01-01T00:10:00-03:00", value=5.0),
        ]
        stats = compute_numeric_stats(pts, "valid")
        assert stats.mean == 5.0
        assert stats.stddev_pop == 0.0
        assert stats.stddev_sample == 0.0

    def test_few_points_stddev_returns_none(self) -> None:
        pts = [AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=5.0)]
        stats = compute_numeric_stats(pts, "valid")
        assert stats.stddev_pop is None
        assert stats.stddev_sample is None
        assert stats.p01 is None
        assert stats.p99 is None

    def test_zero_policy_invalid_removes_zeros(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T00:10:00-03:00", value=20.0),
        ]
        stats = compute_numeric_stats(pts, "invalid")
        assert stats.count == 2
        assert stats.zero_count == 0

    def test_zero_policy_suspicious_keeps_zeros(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T00:10:00-03:00", value=20.0),
        ]
        stats = compute_numeric_stats(pts, "suspicious")
        assert stats.count == 3
        assert stats.zero_count == 1

    def test_zero_policy_valid_keeps_zeros(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=0.0),
        ]
        stats = compute_numeric_stats(pts, "valid")
        assert stats.count == 2
        assert stats.zero_count == 2

    def test_non_good_points_excluded(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0, good=True),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=999.0, good=False),
            AnalysisPoint(timestamp="2026-01-01T00:10:00-03:00", value=20.0, good=True),
        ]
        stats = compute_numeric_stats(pts, "valid")
        assert stats.count == 2
        assert stats.mean == 15.0


class TestGapsInterpolated:
    def test_gap_detected(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=2.0),
            AnalysisPoint(timestamp="2026-01-01T00:25:00-03:00", value=3.0),  # 20 min gap > 15 min
        ]
        gaps = detect_gaps_interpolated(pts)
        assert len(gaps) == 1
        assert gaps[0].method == "interpolated"
        assert gaps[0].duration_seconds > 900

    def test_no_gaps_for_regular(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=2.0),
            AnalysisPoint(timestamp="2026-01-01T00:10:00-03:00", value=3.0),
        ]
        gaps = detect_gaps_interpolated(pts)
        assert len(gaps) == 0


class TestGapsRecorded:
    def test_gap_detected(self) -> None:
        # 10 points at 1 min intervals, then 2 hour gap
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i:02d}:00-03:00", value=float(i))
            for i in range(10)
        ] + [AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=100.0)]
        gaps = detect_gaps_recorded(pts)
        # median of 1-min intervals = 60s, threshold = 60*3=180s
        # gap of 114 min = 6840s >> 180s
        assert len(gaps) == 1
        assert gaps[0].method == "recorded"

    def test_empty_returns_no_gaps(self) -> None:
        gaps = detect_gaps_recorded([])
        assert gaps == []


class TestSpikes:
    def test_zscore_detection(self) -> None:
        # series: [1, 1, 1, 1, 1, 100] — big jump
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=1.0)
            for i in range(5)
        ] + [AnalysisPoint(timestamp="2026-01-01T00:25:00-03:00", value=100.0)]
        spikes, total = detect_spikes(pts)
        assert total >= 1
        assert len(spikes) <= 5

    def test_relative_detection(self) -> None:
        # series with range=10: [0, 0, 0, 0, 0, 6] — relative delta > 50%
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=0.0)
            for i in range(5)
        ] + [AnalysisPoint(timestamp="2026-01-01T00:25:00-03:00", value=6.0)]
        spikes, total = detect_spikes(pts)
        assert total >= 1

    def test_no_spikes_for_constant(self) -> None:
        pts = [
            AnalysisPoint(timestamp=f"2026-01-01T00:{i*5:02d}:00-03:00", value=5.0)
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

    def test_empty_series(self) -> None:
        spikes, total = detect_spikes([])
        assert total == 0
        assert spikes == []
