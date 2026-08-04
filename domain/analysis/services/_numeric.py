from __future__ import annotations

import statistics
from datetime import datetime
from typing import Optional

from domain.analysis.models import (
    AbruptChangeCandidate,
    AnalysisPoint,
    GapCandidate,
    NumericStatistics,
    ZeroPolicy,
)
from domain.analysis.policies import (
    GAP_THRESHOLD_INTERPOLATED_SECONDS,
    GAP_THRESHOLD_RECORDED_FALLBACK_SECONDS,
    SPIKE_RELATIVE_DELTA,
    SPIKE_ROLLING_WINDOW,
    SPIKE_TOP_N,
)


def compute_numeric_stats(
    points: list[AnalysisPoint],
    zero_policy: ZeroPolicy,
) -> NumericStatistics:
    valid = [p for p in points if p.value is not None and p.good]
    if zero_policy == "invalid":
        valid = [p for p in valid if p.value != 0.0]

    values = [p.value for p in valid]
    n = len(values)

    if n == 0:
        return NumericStatistics(count=0)

    total = sum(values)
    mn = min(values)
    mx = max(values)
    avg = total / n
    med = statistics.median(values)

    zero_count = sum(1 for v in values if v == 0.0)

    if n >= 2:
        p01, p99 = _percentiles(values, 100)
        stddev_pop = statistics.pstdev(values)
        stddev_sample = statistics.stdev(values)
    else:
        p01 = p99 = None
        stddev_pop = stddev_sample = None

    return NumericStatistics(
        count=n,
        min=mn,
        max=mx,
        mean=avg,
        median=med,
        p01=p01,
        p99=p99,
        stddev_pop=stddev_pop,
        stddev_sample=stddev_sample,
        sum=total,
        zero_count=zero_count,
    )


def _percentiles(values: list[float], n_buckets: int) -> tuple[float, float]:
    if len(values) < 2:
        return (values[0], values[0]) if values else (0.0, 0.0)
    qs = statistics.quantiles(values, n=n_buckets, method="inclusive")
    return qs[0], qs[-1]


def detect_gaps_interpolated(
    points: list[AnalysisPoint],
    expected_interval_s: int = 300,
    threshold_factor: int = 3,
) -> list[GapCandidate]:
    threshold = expected_interval_s * threshold_factor
    sorted_pts = sorted(points, key=lambda p: p.timestamp)
    gaps: list[GapCandidate] = []
    for i in range(1, len(sorted_pts)):
        t_prev = _parse_ts(sorted_pts[i - 1].timestamp)
        t_cur = _parse_ts(sorted_pts[i].timestamp)
        if t_prev is None or t_cur is None:
            continue
        delta = (t_cur - t_prev).total_seconds()
        if delta > threshold:
            gaps.append(
                GapCandidate(
                    method="interpolated",
                    start_ts=sorted_pts[i - 1].timestamp,
                    end_ts=sorted_pts[i].timestamp,
                    duration_seconds=delta,
                )
            )
    return gaps


def detect_gaps_recorded(
    points: list[AnalysisPoint],
    fallback_s: int = GAP_THRESHOLD_RECORDED_FALLBACK_SECONDS,
    factor: int = 3,
) -> list[GapCandidate]:
    if len(points) < 2:
        return []

    sorted_pts = sorted(points, key=lambda p: p.timestamp)
    deltas: list[float] = []
    for i in range(1, len(sorted_pts)):
        t_prev = _parse_ts(sorted_pts[i - 1].timestamp)
        t_cur = _parse_ts(sorted_pts[i].timestamp)
        if t_prev is None or t_cur is None:
            continue
        delta = (t_cur - t_prev).total_seconds()
        if delta > 0:
            deltas.append(delta)

    if not deltas:
        return []

    median_delta = sorted(deltas)[len(deltas) // 2]
    threshold = median_delta * factor if median_delta > 0 else fallback_s

    gaps: list[GapCandidate] = []
    for i in range(1, len(sorted_pts)):
        t_prev = _parse_ts(sorted_pts[i - 1].timestamp)
        t_cur = _parse_ts(sorted_pts[i].timestamp)
        if t_prev is None or t_cur is None:
            continue
        delta = (t_cur - t_prev).total_seconds()
        if delta > threshold:
            gaps.append(
                GapCandidate(
                    method="recorded",
                    start_ts=sorted_pts[i - 1].timestamp,
                    end_ts=sorted_pts[i].timestamp,
                    duration_seconds=delta,
                )
            )
    return gaps


def detect_spikes(
    points: list[AnalysisPoint],
    window: int = SPIKE_ROLLING_WINDOW,
    rel_threshold: float = SPIKE_RELATIVE_DELTA,
    top_n: int = SPIKE_TOP_N,
) -> tuple[list[AbruptChangeCandidate], int]:
    candidates: list[AbruptChangeCandidate] = []
    vals = [p.value for p in points if p.value is not None]
    if not vals:
        return [], 0
    series_range = max(vals) - min(vals)

    for i in range(1, len(points)):
        prev_pt = points[i - 1]
        cur_pt = points[i]
        if cur_pt.value is None or prev_pt.value is None:
            continue
        if cur_pt.value == prev_pt.value:
            continue

        zscore_basis: str | None = None
        if i >= window:
            window_vals = [
                p.value
                for p in points[i - window : i]
                if p.value is not None
            ]
            if len(window_vals) >= 2:
                mu = sum(window_vals) / len(window_vals)
                var = sum((v - mu) ** 2 for v in window_vals) / len(window_vals)
                sigma = var**0.5
                if sigma > 0:
                    z = abs((cur_pt.value - mu) / sigma)
                    if z > 4.0:
                        zscore_basis = "zscore"

        rel_basis: str | None = None
        if series_range > 0:
            rel_delta = abs(cur_pt.value - prev_pt.value) / series_range
            if rel_delta > rel_threshold:
                rel_basis = "relative"

        if zscore_basis or rel_basis:
            basis: str = (
                "both" if (zscore_basis and rel_basis) else (zscore_basis or rel_basis or "zscore")
            )
            abs_delta = abs(cur_pt.value - prev_pt.value)
            rel_delta_val = (
                abs_delta / series_range if series_range > 0 else 0.0
            )
            candidates.append(
                AbruptChangeCandidate(
                    timestamp=cur_pt.timestamp,
                    previous_value=prev_pt.value,
                    current_value=cur_pt.value,
                    absolute_delta=abs_delta,
                    relative_delta=rel_delta_val,
                    detection_basis=basis,  # type: ignore[arg-type]
                )
            )

    candidates.sort(key=lambda c: c.absolute_delta, reverse=True)
    return candidates[:top_n], len(candidates)


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
