from __future__ import annotations

from domain.analysis.models import AnalysisPoint
from domain.analysis.services._digital import (
    compute_state_durations,
    compute_transitions,
)

STATES = [
    {"indice": 0, "nome": "CLOSED", "descricao": "Closed"},
    {"indice": 1, "nome": "OPEN", "descricao": "Open"},
    {"indice": 2, "nome": "ERROR", "descricao": "Error"},
]


class TestStateDurations:
    def test_basic_durations(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T01:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T03:00:00-03:00", value=0.0),
        ]
        durations = compute_state_durations(pts, STATES, initial_state="CLOSED")
        assert len(durations) >= 2
        states = {d.state for d in durations}
        assert "CLOSED" in states
        assert "OPEN" in states

    def test_percent_sums_to_100(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T06:00:00-03:00", value=0.0),
        ]
        durations = compute_state_durations(pts, STATES, initial_state="CLOSED")
        total_pct = sum(d.percent for d in durations)
        assert abs(total_pct - 100.0) < 1.0

    def test_empty_points(self) -> None:
        durations = compute_state_durations([], STATES)
        assert durations == ()


class TestTransitions:
    def test_transition_count(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T01:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T03:00:00-03:00", value=1.0),
        ]
        transitions = compute_transitions(pts, STATES, initial_state="CLOSED")
        total = sum(t.count for t in transitions)
        assert total == 3

    def test_rate_per_hour(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T01:00:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=0.0),
        ]
        transitions = compute_transitions(pts, STATES, initial_state="CLOSED")
        assert len(transitions) > 0
        assert all(t.rate_per_hour >= 0 for t in transitions)

    def test_single_point_no_transitions(self) -> None:
        pts = [AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0)]
        transitions = compute_transitions(pts, STATES)
        assert transitions == ()

    def test_same_state_no_transitions(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T01:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=0.0),
        ]
        transitions = compute_transitions(pts, STATES)
        assert len(transitions) == 0

    def test_top_transitions_sorted_by_count(self) -> None:
        pts = [
            AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T00:10:00-03:00", value=1.0),
            AnalysisPoint(timestamp="2026-01-01T00:20:00-03:00", value=0.0),
            AnalysisPoint(timestamp="2026-01-01T00:30:00-03:00", value=2.0),
            AnalysisPoint(timestamp="2026-01-01T00:40:00-03:00", value=0.0),
        ]
        transitions = compute_transitions(pts, STATES, initial_state="CLOSED")
        if len(transitions) >= 2:
            assert transitions[0].count >= transitions[1].count
