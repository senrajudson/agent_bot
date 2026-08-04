from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.analysis.models import (
    AnalysisPoint,
    DigitalStateDuration,
    DigitalTransition,
)


def compute_state_durations(
    points: list[AnalysisPoint],
    digital_states: list[dict],
    initial_state: str | None = None,
) -> tuple[DigitalStateDuration, ...]:
    if not points:
        return ()

    state_name_map = {s.get("indice"): s.get("nome", f"state_{s.get('indice')}") for s in digital_states}

    sorted_pts = sorted(points, key=lambda p: p.timestamp)
    total_seconds = _total_duration_seconds(sorted_pts)

    durations: dict[str, float] = {}
    transitions_count: dict[tuple[str, str], int] = {}

    prev_state: str | None = initial_state
    prev_ts: Optional[datetime] = None

    for pt in sorted_pts:
        cur_state = _resolve_state_name(pt.value, state_name_map)
        cur_ts = _parse_ts(pt.timestamp)

        if prev_state is not None and prev_ts is not None and cur_ts is not None:
            delta = (cur_ts - prev_ts).total_seconds()
            if delta > 0:
                durations[prev_state] = durations.get(prev_state, 0) + delta
                if cur_state != prev_state:
                    key = (prev_state, cur_state)
                    transitions_count[key] = transitions_count.get(key, 0) + 1

        if cur_ts is not None:
            prev_ts = cur_ts
        if cur_state is not None:
            prev_state = cur_state

    result: list[DigitalStateDuration] = []
    for state, dur in sorted(durations.items()):
        pct = (dur / total_seconds * 100) if total_seconds > 0 else 0.0
        result.append(
            DigitalStateDuration(
                state=state,
                count=1,
                percent=round(pct, 2),
                duration_seconds=dur,
            )
        )
    return tuple(result)


def compute_transitions(
    points: list[AnalysisPoint],
    digital_states: list[dict],
    initial_state: str | None = None,
) -> tuple[DigitalTransition, ...]:
    if len(points) < 2:
        return ()

    state_name_map = {s.get("indice"): s.get("nome", f"state_{s.get('indice')}") for s in digital_states}

    sorted_pts = sorted(points, key=lambda p: p.timestamp)
    total_hours = _total_duration_hours(sorted_pts)

    transitions: dict[tuple[str, str], int] = {}
    prev_state: str | None = initial_state

    for pt in sorted_pts:
        cur_state = _resolve_state_name(pt.value, state_name_map)
        if prev_state is not None and cur_state is not None and cur_state != prev_state:
            key = (prev_state, cur_state)
            transitions[key] = transitions.get(key, 0) + 1
        if cur_state is not None:
            prev_state = cur_state

    result: list[DigitalTransition] = []
    for (from_s, to_s), count in sorted(transitions.items(), key=lambda x: -x[1]):
        rate = count / total_hours if total_hours > 0 else 0.0
        result.append(
            DigitalTransition(
                from_state=from_s,
                to_state=to_s,
                count=count,
                rate_per_hour=round(rate, 4),
            )
        )
    return tuple(result)


def _resolve_state_name(value: float | None, state_map: dict) -> str:
    if value is None:
        return "unknown"
    idx = int(value)
    return state_map.get(idx, f"state_{idx}")


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _total_duration_seconds(points: list[AnalysisPoint]) -> float:
    if len(points) < 2:
        return 0.0
    first = _parse_ts(points[0].timestamp)
    last = _parse_ts(points[-1].timestamp)
    if first is None or last is None:
        return 0.0
    return (last - first).total_seconds()


def _total_duration_hours(points: list[AnalysisPoint]) -> float:
    return _total_duration_seconds(points) / 3600.0
