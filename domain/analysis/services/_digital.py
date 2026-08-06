from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from domain.analysis.models import (
    AnalysisPoint,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalStateDuration,
    DigitalStateOccupancy,
    DigitalStateRef,
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


# ---------------------------------------------------------------------------
# Novo motor temporal para tags digitais
# ---------------------------------------------------------------------------

_TOLERANCE_SECONDS = 0.1


class _SegmentKind(Enum):
    KNOWN = "known"
    BAD = "bad"
    NULL = "null"
    UNKNOWN = "unknown"
    UNCOVERED = "uncovered"


def reconstruct_timeline(
    window_start: datetime,
    window_end: datetime,
    seed: AnalysisPoint | None,
    recorded: list[AnalysisPoint],
    possible_states: list[dict],
) -> DigitalAnalysisResult:
    """Reconstrói a timeline digital com ocupação por duração e buckets de integridade."""

    # Etapa 1 — Validar janela
    if window_end <= window_start:
        raise ValueError("window_end deve ser posterior a window_start")
    window_seconds = (window_end - window_start).total_seconds()

    # Etapa 2 — Normalizar Digital Set
    state_code_map: dict[int, dict] = {}
    state_ref_map: dict[int, DigitalStateRef] = {}
    for s in possible_states:
        code = s.get("indice")
        if code is not None:
            int_code = int(code)
            state_code_map[int_code] = s
            state_ref_map[int_code] = DigitalStateRef(
                state_code=int_code,
                state_name=s.get("nome", f"state_{int_code}"),
            )
    possible_refs = tuple(state_ref_map.values())

    # Etapa 3 — Normalizar eventos
    events: list[AnalysisPoint] = []
    if seed is not None:
        events.append(seed)
    for pt in recorded:
        ts = _parse_ts(pt.timestamp)
        if ts is not None and ts < window_end:
            events.append(pt)
    events.sort(key=lambda p: p.timestamp)

    # Etapa 4 — Deduplicar
    deduped: list[AnalysisPoint] = []
    seen: set[tuple] = set()
    for pt in events:
        key = (pt.timestamp, pt.value, pt.good, pt.questionable, pt.substituted)
        if key not in seen:
            seen.add(key)
            deduped.append(pt)
    events = deduped

    # Etapa 5 — Classificar eventos
    classified: list[tuple[datetime, _SegmentKind, int | None, AnalysisPoint]] = []
    for pt in events:
        ts = _parse_ts(pt.timestamp)
        if ts is None:
            continue
        if pt.value is None:
            kind = _SegmentKind.NULL
            code = None
        elif not pt.good:
            kind = _SegmentKind.BAD
            code = int(pt.value)
        elif int(pt.value) not in state_code_map:
            kind = _SegmentKind.UNKNOWN
            code = int(pt.value)
        else:
            kind = _SegmentKind.KNOWN
            code = int(pt.value)
        classified.append((ts, kind, code, pt))

    # Etapa 6 — Construir segmentos
    segments: list[tuple[float, _SegmentKind, int | None]] = []
    prev_ts = window_start
    prev_kind = _SegmentKind.UNCOVERED
    prev_code: int | None = None

    for ts, kind, code, _pt in classified:
        if ts < window_start:
            ts = window_start
        if ts >= window_end:
            break
        delta = (ts - prev_ts).total_seconds()
        if delta > 0:
            segments.append((delta, prev_kind, prev_code))
        prev_ts = ts
        prev_kind = kind
        prev_code = code

    # Último segmento até window_end
    delta = (window_end - prev_ts).total_seconds()
    if delta > 0:
        segments.append((delta, prev_kind, prev_code))

    # Etapa 7 — Buckets exclusivos
    known_seconds = 0.0
    bad_seconds = 0.0
    null_seconds = 0.0
    unknown_seconds = 0.0
    uncovered_seconds = 0.0
    questionable_seconds = 0.0
    substituted_seconds = 0.0

    # Para overlays, rastreamos por segmento Known
    for dur, kind, _code in segments:
        if kind == _SegmentKind.KNOWN:
            known_seconds += dur
        elif kind == _SegmentKind.BAD:
            bad_seconds += dur
        elif kind == _SegmentKind.NULL:
            null_seconds += dur
        elif kind == _SegmentKind.UNKNOWN:
            unknown_seconds += dur
        else:
            uncovered_seconds += dur

    # Etapa 8 — Overlays (Questionable/Substituted)
    # Recalcular sobre segmentos Known
    prev_ts_overlay = window_start
    for ts, kind, _code, pt in classified:
        if ts < window_start:
            ts = window_start
        if ts >= window_end:
            break
        if kind == _SegmentKind.KNOWN:
            # Calcular duração deste ponto até o próximo
            next_ts = window_end
            for ts2, _, _, _ in classified:
                if ts2 > ts:
                    next_ts = ts2
                    break
            if next_ts > window_end:
                next_ts = window_end
            dur = (next_ts - ts).total_seconds()
            if dur > 0 and known_seconds > 0:
                if pt.questionable:
                    questionable_seconds += dur
                if pt.substituted:
                    substituted_seconds += dur

    # Etapa 9 — Ocupação
    occupancy_map: dict[int, float] = {}
    entries_map: dict[int, int] = {}
    current_known_code: int | None = None

    for dur, kind, code in segments:
        if kind == _SegmentKind.KNOWN and code is not None:
            occupancy_map[code] = occupancy_map.get(code, 0.0) + dur
            if code != current_known_code:
                entries_map[code] = entries_map.get(code, 0) + 1
                current_known_code = code
        else:
            current_known_code = None

    occupancy: list[DigitalStateOccupancy] = []
    for ref in possible_refs:
        code = int(ref.state_code)
        dur = occupancy_map.get(code, 0.0)
        pct = (dur / window_seconds * 100) if window_seconds > 0 else 0.0
        entries = entries_map.get(code, 0)
        occupancy.append(DigitalStateOccupancy(
            state_code=ref.state_code,
            state_name=ref.state_name,
            duration_seconds=round(dur, 4),
            percentage_of_window=round(pct, 2),
            entries_count=entries,
        ))
    occupancy.sort(key=lambda o: (-o.duration_seconds, o.state_code))

    # Etapa 10 — Transições
    transitions: list[DigitalTransition] = []
    prev_known: int | None = None
    for dur, kind, code in segments:
        if kind == _SegmentKind.KNOWN and code is not None:
            if prev_known is not None and code != prev_known:
                from_ref = state_ref_map.get(prev_known)
                to_ref = state_ref_map.get(code)
                if from_ref and to_ref:
                    key = (from_ref.state_name, to_ref.state_name)
                    existing = next((t for t in transitions if (t.from_state, t.to_state) == key), None)
                    if existing:
                        # Atualizar contagem (manter como 1 por transição de segmento)
                        pass
                    else:
                        total_hours = window_seconds / 3600.0
                        rate = 1.0 / total_hours if total_hours > 0 else 0.0
                        transitions.append(DigitalTransition(
                            from_state=from_ref.state_name,
                            to_state=to_ref.state_name,
                            count=1,
                            rate_per_hour=round(rate, 4),
                        ))
            prev_known = code
        else:
            prev_known = None

    # Etapa 11 — Estado inicial e final
    initial_state: DigitalStateRef | None = None
    final_state: DigitalStateRef | None = None

    for dur, kind, code in segments:
        if kind == _SegmentKind.KNOWN and code is not None:
            if initial_state is None:
                initial_state = state_ref_map.get(code)
            final_state = state_ref_map.get(code)

    # Etapa 12 — Determinar status
    has_known = known_seconds > _TOLERANCE_SECONDS
    has_uncovered = uncovered_seconds > _TOLERANCE_SECONDS
    has_transitions = len(transitions) > 0

    # Precedência: NO_DATA > INVALID > PARTIAL > NO_TRANSITIONS > COMPLETE
    if not events:
        status = DigitalAnalysisStatus.NO_DATA
    elif not has_known:
        status = DigitalAnalysisStatus.INVALID_DIGITAL_VALUES
    elif has_uncovered:
        status = DigitalAnalysisStatus.PARTIAL_COVERAGE
    elif not has_transitions:
        status = DigitalAnalysisStatus.NO_TRANSITIONS
    else:
        status = DigitalAnalysisStatus.COMPLETE

    # Invariante de fechamento
    total_exclusive = known_seconds + bad_seconds + null_seconds + unknown_seconds + uncovered_seconds
    if abs(total_exclusive - window_seconds) > _TOLERANCE_SECONDS:
        import logging
        logging.getLogger(__name__).warning(
            "Digital timeline partition does not close: expected %.2f, got %.2f",
            window_seconds, total_exclusive,
        )

    # Percentuais
    known_pct = (known_seconds / window_seconds * 100) if window_seconds > 0 else 0.0
    bad_pct = (bad_seconds / window_seconds * 100) if window_seconds > 0 else 0.0
    null_pct = (null_seconds / window_seconds * 100) if window_seconds > 0 else 0.0
    unknown_pct = (unknown_seconds / window_seconds * 100) if window_seconds > 0 else 0.0
    uncovered_pct = (uncovered_seconds / window_seconds * 100) if window_seconds > 0 else 0.0
    questionable_pct = (questionable_seconds / known_seconds * 100) if known_seconds > 0 else 0.0
    substituted_pct = (substituted_seconds / known_seconds * 100) if known_seconds > 0 else 0.0

    coverage = DigitalCoverageMetrics(
        window_seconds=round(window_seconds, 4),
        known_seconds=round(known_seconds, 4),
        known_pct=round(known_pct, 2),
        bad_seconds=round(bad_seconds, 4),
        bad_pct=round(bad_pct, 2),
        null_seconds=round(null_seconds, 4),
        null_pct=round(null_pct, 2),
        unknown_seconds=round(unknown_seconds, 4),
        unknown_pct=round(unknown_pct, 2),
        uncovered_seconds=round(uncovered_seconds, 4),
        uncovered_pct=round(uncovered_pct, 2),
        questionable_seconds=round(questionable_seconds, 4),
        questionable_pct=round(questionable_pct, 2),
        substituted_seconds=round(substituted_seconds, 4),
        substituted_pct=round(substituted_pct, 2),
    )

    warnings: list[str] = []
    if not events and seed is None:
        warnings.append("Nenhum evento registrado e seed ausente na janela.")
    if has_uncovered:
        warnings.append(f"Cobertura parcial: {uncovered_pct:.1f}% da janela sem estado conhecido.")

    valid_events_count = sum(1 for _, kind, _, _ in classified if kind == _SegmentKind.KNOWN)

    return DigitalAnalysisResult(
        status=status,
        possible_states=possible_refs,
        initial_state=initial_state,
        final_state=final_state,
        occupancy=tuple(occupancy),
        transitions=tuple(transitions),
        coverage=coverage,
        recorded_events_count=len(recorded),
        valid_events_count=valid_events_count,
        warnings=tuple(warnings),
    )
