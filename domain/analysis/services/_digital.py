from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from domain.analysis.models import (
    AnalysisPoint,
    DailyBucket,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalDiagnosticWarning,
    DigitalRecordedEvent,
    DigitalSetSnapshotEntry,
    DigitalStateDuration,
    DigitalStateOccupancy,
    DigitalStateRef,
    DigitalTransition,
    QualitySummary,
    SegmentKind,
    SegmentSource,
    SeedInfo,
    StateStatistic,
    TimelineSegment,
    TransitionStatistic,
    UnknownValueStatistic,
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


# ---------------------------------------------------------------------------
# Helper de formatação de duração
# ---------------------------------------------------------------------------


def format_duration(seconds: float) -> str:
    """Converte segundos em string legível: '1d 02h 03m 04s'."""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    d = total // 86400
    h = (total % 86400) // 3600
    m = (total % 3600) // 60
    s = total % 60
    parts: list[str] = []
    if d > 0:
        parts.append(f"{d}d")
    if h > 0:
        parts.append(f"{h:02d}h")
    if m > 0:
        parts.append(f"{m:02d}m")
    parts.append(f"{s:02d}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Enriquecimento do resultado digital (facts adicionais)
# ---------------------------------------------------------------------------

_SK_MAP: dict[_SegmentKind, SegmentKind] = {
    _SegmentKind.KNOWN: SegmentKind.KNOWN,
    _SegmentKind.BAD: SegmentKind.BAD,
    _SegmentKind.UNKNOWN: SegmentKind.UNKNOWN,
    _SegmentKind.NULL: SegmentKind.NULL,
    _SegmentKind.UNCOVERED: SegmentKind.UNCOVERED,
}


def _classify_event(
    pt: AnalysisPoint,
    state_code_map: dict[int, dict],
) -> tuple[SegmentKind, int | None]:
    """Classifica um evento usando a mesma lógica de reconstruct_timeline."""
    if pt.value is None:
        return SegmentKind.NULL, None
    if not pt.good:
        return SegmentKind.BAD, int(pt.value)
    if int(pt.value) not in state_code_map:
        return SegmentKind.UNKNOWN, int(pt.value)
    return SegmentKind.KNOWN, int(pt.value)


def _build_state_code_map(possible_states: list[dict]) -> dict[int, dict]:
    return {int(s["indice"]): s for s in possible_states if s.get("indice") is not None}


def _build_state_ref_map(possible_states: list[dict]) -> dict[int, DigitalStateRef]:
    return {
        int(s["indice"]): DigitalStateRef(
            state_code=int(s["indice"]),
            state_name=s.get("nome", f"state_{int(s['indice'])}"),
        )
        for s in possible_states
        if s.get("indice") is not None
    }


def _build_classified_events(
    seed: AnalysisPoint | None,
    recorded: list[AnalysisPoint],
    state_code_map: dict[int, dict],
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, SegmentKind, int | None, AnalysisPoint]]:
    """Classifica seed + recorded (após dedup) usando a mesma lógica do motor."""
    events: list[AnalysisPoint] = []
    if seed is not None:
        events.append(seed)
    for pt in recorded:
        ts = _parse_ts(pt.timestamp)
        if ts is not None and ts < window_end:
            events.append(pt)
    events.sort(key=lambda p: p.timestamp)

    deduped: list[AnalysisPoint] = []
    seen: set[tuple] = set()
    for pt in events:
        key = (pt.timestamp, pt.value, pt.good, pt.questionable, pt.substituted)
        if key not in seen:
            seen.add(key)
            deduped.append(pt)

    classified: list[tuple[datetime, SegmentKind, int | None, AnalysisPoint]] = []
    for pt in deduped:
        ts = _parse_ts(pt.timestamp)
        if ts is None:
            continue
        kind, code = _classify_event(pt, state_code_map)
        classified.append((ts, kind, code, pt))
    return classified


def _build_timeline_segments(
    classified: list[tuple[datetime, SegmentKind, int | None, AnalysisPoint]],
    seed: AnalysisPoint | None,
    recorded: list[AnalysisPoint],
    state_code_map: dict[int, dict],
    state_ref_map: dict[int, DigitalStateRef],
    window_start: datetime,
    window_end: datetime,
) -> tuple[TimelineSegment, ...]:
    """Constrói TimelineSegment com source preservado."""
    segments: list[TimelineSegment] = []
    prev_ts = window_start
    prev_kind = SegmentKind.UNCOVERED
    prev_code: int | None = None
    prev_pt: AnalysisPoint | None = None
    prev_source: SegmentSource | None = None

    # Mapear timestamp → source
    seed_ts = _parse_ts(seed.timestamp) if seed is not None else None

    for ts, kind, code, pt in classified:
        if ts < window_start:
            ts = window_start
        if ts >= window_end:
            break
        delta = (ts - prev_ts).total_seconds()
        if delta > 0:
            ref = state_ref_map.get(prev_code) if prev_code is not None else None
            segments.append(TimelineSegment(
                start=prev_ts,
                end=ts,
                duration_seconds=round(delta, 4),
                raw_value=prev_pt.value if prev_pt is not None else None,
                state_code=prev_code,
                state_name=ref.state_name if ref else None,
                kind=prev_kind,
                good=prev_pt.good if prev_pt is not None else None,
                questionable=prev_pt.questionable if prev_pt is not None else None,
                substituted=prev_pt.substituted if prev_pt is not None else None,
                source=prev_source,
            ))
        prev_ts = ts
        prev_kind = kind
        prev_code = code
        prev_pt = pt
        # Determinar source
        pt_ts = _parse_ts(pt.timestamp)
        if seed_ts is not None and pt_ts is not None and pt_ts == seed_ts:
            prev_source = SegmentSource.SEED_AT_OR_BEFORE
        else:
            prev_source = SegmentSource.RECORDED

    # Último segmento até window_end
    delta = (window_end - prev_ts).total_seconds()
    if delta > 0:
        ref = state_ref_map.get(prev_code) if prev_code is not None else None
        segments.append(TimelineSegment(
            start=prev_ts,
            end=window_end,
            duration_seconds=round(delta, 4),
            raw_value=prev_pt.value if prev_pt is not None else None,
            state_code=prev_code,
            state_name=ref.state_name if ref else None,
            kind=prev_kind,
            good=prev_pt.good if prev_pt is not None else None,
            questionable=prev_pt.questionable if prev_pt is not None else None,
            substituted=prev_pt.substituted if prev_pt is not None else None,
            source=prev_source if prev_kind != SegmentKind.UNCOVERED else None,
        ))

    return tuple(segments)


def _build_classified_recorded_events(
    recorded: list[AnalysisPoint],
    state_code_map: dict[int, dict],
    state_ref_map: dict[int, DigitalStateRef],
) -> tuple[DigitalRecordedEvent, ...]:
    """Classifica eventos Recorded (após dedup, sem seed)."""
    seen: set[tuple] = set()
    events: list[DigitalRecordedEvent] = []
    for pt in recorded:
        key = (pt.timestamp, pt.value, pt.good, pt.questionable, pt.substituted)
        if key in seen:
            continue
        seen.add(key)
        kind, code = _classify_event(pt, state_code_map)
        ref = state_ref_map.get(code) if code is not None else None
        events.append(DigitalRecordedEvent(
            timestamp=pt.timestamp,
            raw_value=pt.value,
            resolved_code=code,
            resolved_state=ref.state_name if ref else None,
            classification=kind,
            good=pt.good,
            questionable=pt.questionable,
            substituted=pt.substituted,
        ))
    events.sort(key=lambda e: e.timestamp)
    return tuple(events)


def _build_seed_info(
    seed: AnalysisPoint | None,
    state_code_map: dict[int, dict],
    state_ref_map: dict[int, DigitalStateRef],
    window_start: datetime,
) -> SeedInfo | None:
    if seed is None:
        return SeedInfo(
            found=False, timestamp=None, raw_value=None,
            good=None, questionable=None, substituted=None,
            classification=None, age_seconds_at_window_start=None,
            state_code=None, state_name=None,
        )
    kind, code = _classify_event(seed, state_code_map)
    ref = state_ref_map.get(code) if code is not None else None
    seed_ts = _parse_ts(seed.timestamp)
    age = None
    if seed_ts is not None:
        age = (window_start - seed_ts).total_seconds()
        if age < 0:
            age = None
    return SeedInfo(
        found=True,
        timestamp=seed.timestamp,
        raw_value=seed.value,
        good=seed.good,
        questionable=seed.questionable,
        substituted=seed.substituted,
        classification=kind,
        age_seconds_at_window_start=age,
        state_code=ref.state_code if ref else code,
        state_name=ref.state_name if ref else None,
    )


def _build_state_statistics(
    segments: tuple[TimelineSegment, ...],
    possible_refs: dict[int, DigitalStateRef],
    window_seconds: float,
) -> tuple[StateStatistic, ...]:
    """Calcula estatísticas por estado a partir dos segmentos."""
    # Agregar por state_code (apenas KNOWN)
    state_data: dict[int, dict] = {}
    for ref in possible_refs.values():
        state_data[int(ref.state_code)] = {
            "code": ref.state_code,
            "name": ref.state_name,
            "durations": [],
            "first_seen": None,
            "last_seen": None,
            "longest_start": None,
            "longest_end": None,
            "longest_dur": 0.0,
            "entries": 0,
            "exits": 0,
        }

    current_known_code: int | None = None
    for seg in segments:
        if seg.kind == SegmentKind.KNOWN and seg.state_code is not None:
            code = int(seg.state_code)
            if code not in state_data:
                state_data[code] = {
                    "code": seg.state_code, "name": seg.state_name,
                    "durations": [], "first_seen": None, "last_seen": None,
                    "longest_start": None, "longest_end": None, "longest_dur": 0.0,
                    "entries": 0, "exits": 0,
                }
            d = state_data[code]
            d["durations"].append(seg.duration_seconds)
            if d["first_seen"] is None or seg.start < d["first_seen"]:
                d["first_seen"] = seg.start
            if d["last_seen"] is None or seg.end > d["last_seen"]:
                d["last_seen"] = seg.end
            if seg.duration_seconds > d["longest_dur"]:
                d["longest_dur"] = seg.duration_seconds
                d["longest_start"] = seg.start
                d["longest_end"] = seg.end
            if code != current_known_code:
                d["entries"] += 1
                if current_known_code is not None and current_known_code in state_data:
                    state_data[current_known_code]["exits"] += 1
                current_known_code = code
        else:
            if current_known_code is not None and current_known_code in state_data:
                state_data[current_known_code]["exits"] += 1
            current_known_code = None

    result: list[StateStatistic] = []
    for ref in possible_refs.values():
        code = int(ref.state_code)
        d = state_data.get(code, {
            "code": ref.state_code, "name": ref.state_name,
            "durations": [], "first_seen": None, "last_seen": None,
            "longest_start": None, "longest_end": None, "longest_dur": 0.0,
            "entries": 0, "exits": 0,
        })
        durs = d["durations"]
        observed = len(durs) > 0
        total_dur = sum(durs)
        pct = (total_dur / window_seconds * 100) if window_seconds > 0 else 0.0
        import statistics as _stat
        dwell_avg = _stat.mean(durs) if durs else None
        dwell_med = _stat.median(durs) if durs else None
        dwell_min = min(durs) if durs else None
        dwell_max = max(durs) if durs else None
        result.append(StateStatistic(
            state_code=ref.state_code,
            state_name=ref.state_name,
            observed=observed,
            entries_count=d["entries"],
            exits_count=d["exits"],
            segment_count=len(durs),
            duration_seconds=round(total_dur, 4),
            percentage_of_window=round(pct, 2),
            first_seen=d["first_seen"],
            last_seen=d["last_seen"],
            longest_segment_start=d["longest_start"],
            longest_segment_end=d["longest_end"],
            dwell_avg_seconds=round(dwell_avg, 4) if dwell_avg is not None else None,
            dwell_median_seconds=round(dwell_med, 4) if dwell_med is not None else None,
            dwell_min_seconds=round(dwell_min, 4) if dwell_min is not None else None,
            dwell_max_seconds=round(dwell_max, 4) if dwell_max is not None else None,
        ))
    return tuple(result)


def _build_transition_statistics(
    segments: tuple[TimelineSegment, ...],
    window_seconds: float,
) -> tuple[TransitionStatistic, ...]:
    """Transições com kind/code/timestamps entre segmentos consecutivos."""
    pairs: dict[tuple, dict] = {}
    prev_seg: TimelineSegment | None = None
    for seg in segments:
        if prev_seg is not None:
            from_k = prev_seg.kind
            to_k = seg.kind
            # Pular se ambos UNCOVERED ou sem mudança
            if from_k == SegmentKind.UNCOVERED and to_k == SegmentKind.UNCOVERED:
                prev_seg = seg
                continue
            from_code = prev_seg.state_code
            from_name = prev_seg.state_name
            to_code = seg.state_code
            to_name = seg.state_name
            key = (from_k, from_code, from_name, to_k, to_code, to_name)
            if key not in pairs:
                pairs[key] = {
                    "from_kind": from_k, "from_code": from_code, "from_name": from_name,
                    "to_kind": to_k, "to_code": to_code, "to_name": to_name,
                    "count": 0, "first": None, "last": None,
                }
            p = pairs[key]
            p["count"] += 1
            if p["first"] is None or seg.start < p["first"]:
                p["first"] = seg.start
            if p["last"] is None or seg.end > p["last"]:
                p["last"] = seg.end
        prev_seg = seg

    total = sum(p["count"] for p in pairs.values())
    result: list[TransitionStatistic] = []
    for key, p in sorted(pairs.items(), key=lambda x: -x[1]["count"]):
        pct = (p["count"] / total * 100) if total > 0 else 0.0
        result.append(TransitionStatistic(
            from_kind=p["from_kind"],
            from_code=p["from_code"],
            from_name=p["from_name"],
            to_kind=p["to_kind"],
            to_code=p["to_code"],
            to_name=p["to_name"],
            count=p["count"],
            first_transition=p["first"],
            last_transition=p["last"],
            percentage_of_transitions=round(pct, 2),
        ))
    return tuple(result)


def _build_unknown_value_statistics(
    segments: tuple[TimelineSegment, ...],
    classified: list[tuple[datetime, SegmentKind, int | None, AnalysisPoint]],
    window_seconds: float,
) -> tuple[UnknownValueStatistic, ...]:
    """Agrega unknown values por raw_value."""
    unknown_events: dict[float | int, list] = {}
    unknown_segments: dict[float | int, list] = {}

    for seg in segments:
        if seg.kind == SegmentKind.UNKNOWN and seg.raw_value is not None:
            rv = seg.raw_value
            if rv not in unknown_segments:
                unknown_segments[rv] = []
            unknown_segments[rv].append(seg)

    for ts, kind, code, pt in classified:
        if kind == SegmentKind.UNKNOWN and pt.value is not None:
            rv = pt.value
            if rv not in unknown_events:
                unknown_events[rv] = []
            unknown_events[rv].append(pt)

    result: list[UnknownValueStatistic] = []
    for rv in sorted(set(list(unknown_events.keys()) + list(unknown_segments.keys()))):
        evts = unknown_events.get(rv, [])
        segs = unknown_segments.get(rv, [])
        total_dur = sum(s.duration_seconds for s in segs)
        pct = (total_dur / window_seconds * 100) if window_seconds > 0 else 0.0
        first = min((s.start for s in segs), default=None)
        last = max((s.end for s in segs), default=None)
        sample = evts[0].timestamp if evts else None
        result.append(UnknownValueStatistic(
            raw_value=rv,
            occurrences=len(evts),
            segment_count=len(segs),
            duration_seconds=round(total_dur, 4),
            percentage_of_window=round(pct, 2),
            first_seen=first,
            last_seen=last,
            sample_timestamp=sample,
        ))
    result.sort(key=lambda u: (-u.duration_seconds, u.raw_value))
    return tuple(result)


def _build_quality_summary(
    classified: list[tuple[datetime, SegmentKind, int | None, AnalysisPoint]],
    segments: tuple[TimelineSegment, ...],
    coverage: DigitalCoverageMetrics,
    recorded: list[AnalysisPoint],
    seed: AnalysisPoint | None,
) -> QualitySummary:
    """Quality summary separando event counts de timeline coverage."""
    # Event counts (após dedup, sem seed)
    seen_events: set[tuple] = set()
    good_ev = 0
    bad_ev = 0
    questionable_ev = 0
    substituted_ev = 0
    for ts, kind, code, pt in classified:
        key = (pt.timestamp, pt.value, pt.good, pt.questionable, pt.substituted)
        # Pular seed
        if seed is not None and pt.timestamp == seed.timestamp and pt.value == seed.value:
            continue
        if key in seen_events:
            continue
        seen_events.add(key)
        if pt.good:
            good_ev += 1
        else:
            bad_ev += 1
        if pt.questionable:
            questionable_ev += 1
        if pt.substituted:
            substituted_ev += 1
    total_ev = good_ev + bad_ev

    # Longest BAD/UNKNOWN
    longest_bad_start = None
    longest_bad_end = None
    longest_bad_dur = 0.0
    longest_unk_start = None
    longest_unk_end = None
    longest_unk_dur = 0.0
    bad_seg_count = 0
    unk_seg_count = 0
    first_bad = None
    last_bad = None

    for seg in segments:
        if seg.kind == SegmentKind.BAD:
            bad_seg_count += 1
            if first_bad is None or seg.start < first_bad:
                first_bad = seg.start
            if last_bad is None or seg.end > last_bad:
                last_bad = seg.end
            if seg.duration_seconds > longest_bad_dur:
                longest_bad_dur = seg.duration_seconds
                longest_bad_start = seg.start
                longest_bad_end = seg.end
            elif seg.duration_seconds == longest_bad_dur and longest_bad_start is not None:
                if seg.start < longest_bad_start:
                    longest_bad_start = seg.start
                    longest_bad_end = seg.end
        elif seg.kind == SegmentKind.UNKNOWN:
            unk_seg_count += 1
            if seg.duration_seconds > longest_unk_dur:
                longest_unk_dur = seg.duration_seconds
                longest_unk_start = seg.start
                longest_unk_end = seg.end
            elif seg.duration_seconds == longest_unk_dur and longest_unk_start is not None:
                if seg.start < longest_unk_start:
                    longest_unk_start = seg.start
                    longest_unk_end = seg.end

    return QualitySummary(
        total_events=total_ev,
        good_events=good_ev,
        bad_events=bad_ev,
        questionable_events=questionable_ev,
        substituted_events=substituted_ev,
        known_duration=coverage.known_seconds,
        bad_duration=coverage.bad_seconds,
        unknown_duration=coverage.unknown_seconds,
        null_duration=coverage.null_seconds,
        uncovered_duration=coverage.uncovered_seconds,
        questionable_duration=coverage.questionable_seconds,
        questionable_pct=coverage.questionable_pct,
        substituted_duration=coverage.substituted_seconds,
        substituted_pct=coverage.substituted_pct,
        bad_segment_count=bad_seg_count,
        unknown_segment_count=unk_seg_count,
        longest_bad_start=longest_bad_start,
        longest_bad_end=longest_bad_end,
        longest_bad_duration=round(longest_bad_dur, 4),
        longest_unknown_start=longest_unk_start,
        longest_unknown_end=longest_unk_end,
        longest_unknown_duration=round(longest_unk_dur, 4),
        first_bad_timestamp=first_bad.isoformat() if first_bad is not None else None,
        last_bad_timestamp=last_bad.isoformat() if last_bad is not None else None,
    )


def _build_daily_summary(
    segments: tuple[TimelineSegment, ...],
    transitions: tuple[TransitionStatistic, ...],
    window_start: datetime,
    window_end: datetime,
    window_seconds: float,
) -> tuple[DailyBucket, ...]:
    """Resumo diário com split virtual de midnight."""
    if window_seconds <= 86400:
        return ()

    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Sao_Paulo")

    # Determinar dias na janela
    start_local = window_start.astimezone(tz)
    end_local = window_end.astimezone(tz)
    from datetime import date, timedelta
    current_date = start_local.date()
    end_date = end_local.date()

    buckets: list[DailyBucket] = []
    while current_date <= end_date:
        from datetime import datetime as _dt
        day_start_local = _dt.combine(current_date, _dt.min.time()).replace(tzinfo=tz)
        day_end_local = _dt.combine(current_date + timedelta(days=1), _dt.min.time()).replace(tzinfo=tz)

        # Interseção com janela
        inter_start = max(day_start_local, window_start) if day_start_local >= window_start else window_start
        inter_end = min(day_end_local, window_end) if day_end_local <= window_end else window_end

        if inter_start >= inter_end:
            current_date += timedelta(days=1)
            continue

        inter_secs = (inter_end - inter_start).total_seconds()
        if inter_secs <= 0:
            current_date += timedelta(days=1)
            continue

        # Calcular coverage por bucket
        known_s = 0.0
        bad_s = 0.0
        unknown_s = 0.0
        null_s = 0.0
        uncovered_s = 0.0
        states_in_bucket: dict[int, float] = {}
        unknown_vals_in_bucket: set = set()

        for seg in segments:
            seg_start = seg.start if hasattr(seg.start, 'astimezone') else seg.start
            seg_end = seg.end if hasattr(seg.end, 'astimezone') else seg.end
            if not hasattr(seg_start, 'astimezone'):
                continue
            # Interseção
            ov_start = max(seg_start, inter_start)
            ov_end = min(seg_end, inter_end)
            if ov_start >= ov_end:
                continue
            ov_secs = (ov_end - ov_start).total_seconds()
            if seg.kind == SegmentKind.KNOWN:
                known_s += ov_secs
                if seg.state_code is not None:
                    c = int(seg.state_code)
                    states_in_bucket[c] = states_in_bucket.get(c, 0.0) + ov_secs
            elif seg.kind == SegmentKind.BAD:
                bad_s += ov_secs
            elif seg.kind == SegmentKind.UNKNOWN:
                unknown_s += ov_secs
                if seg.raw_value is not None:
                    unknown_vals_in_bucket.add(seg.raw_value)
            elif seg.kind == SegmentKind.NULL:
                null_s += ov_secs
            else:
                uncovered_s += ov_secs

        total_cov = known_s + bad_s + unknown_s + null_s + uncovered_s
        def _pct(v: float) -> float:
            return round((v / inter_secs * 100), 2) if inter_secs > 0 else 0.0

        # Dominant KNOWN state
        dom_code = None
        dom_name = None
        dom_pct = None
        if states_in_bucket:
            dom_code_int = max(states_in_bucket, key=states_in_bucket.get)
            dom_code = dom_code_int
            dom_pct = round(states_in_bucket[dom_code_int] / inter_secs * 100, 2) if inter_secs > 0 else 0.0
            # Resolver nome
            for seg in segments:
                if seg.kind == SegmentKind.KNOWN and seg.state_code is not None and int(seg.state_code) == dom_code_int:
                    dom_name = seg.state_name
                    break

        # Transições no dia
        trans_count = 0
        for t in transitions:
            if t.first_transition is not None and hasattr(t.first_transition, 'date'):
                if t.first_transition.astimezone(tz).date() == current_date:
                    trans_count += t.count

        buckets.append(DailyBucket(
            date=current_date.isoformat(),
            known_pct=_pct(known_s),
            bad_pct=_pct(bad_s),
            unknown_pct=_pct(unknown_s),
            null_pct=_pct(null_s),
            uncovered_pct=_pct(uncovered_s),
            transition_count=trans_count,
            dominant_state_code=dom_code,
            dominant_state_name=dom_name,
            dominant_state_pct=dom_pct,
            distinct_states_observed=len(states_in_bucket),
            distinct_unknown_values=len(unknown_vals_in_bucket),
        ))
        current_date += timedelta(days=1)

    return tuple(buckets)


def _build_diagnostic_warnings(
    base: DigitalAnalysisResult,
    seed_info: SeedInfo | None,
    unknown_stats: tuple[UnknownValueStatistic, ...],
) -> tuple[DigitalDiagnosticWarning, ...]:
    """Warnings determinísticos emitidos pelo domain."""
    warnings: list[DigitalDiagnosticWarning] = []
    cov = base.coverage

    if unknown_stats:
        warnings.append(DigitalDiagnosticWarning(
            code="UNKNOWN_DIGITAL_VALUES", severity="WARNING"))

    if cov.known_seconds <= _TOLERANCE_SECONDS and base.status != DigitalAnalysisStatus.NO_DATA:
        warnings.append(DigitalDiagnosticWarning(
            code="NO_KNOWN_DIGITAL_STATES", severity="WARNING"))

    if cov.uncovered_seconds > _TOLERANCE_SECONDS:
        warnings.append(DigitalDiagnosticWarning(
            code="PARTIAL_TIMELINE_COVERAGE", severity="WARNING"))

    if seed_info is not None and seed_info.classification == SegmentKind.BAD:
        warnings.append(DigitalDiagnosticWarning(
            code="SEED_BAD_QUALITY", severity="WARNING"))

    if cov.bad_seconds > _TOLERANCE_SECONDS and base.status != DigitalAnalysisStatus.INVALID_DIGITAL_VALUES:
        warnings.append(DigitalDiagnosticWarning(
            code="BAD_QUALITY_COVERAGE", severity="WARNING"))

    return tuple(warnings)


def _build_digital_set_snapshot(
    possible_states: list[dict],
) -> tuple[DigitalSetSnapshotEntry, ...]:
    """Snapshot do Digital Set com code/name/description."""
    entries: list[DigitalSetSnapshotEntry] = []
    for s in possible_states:
        code = s.get("indice")
        if code is not None:
            entries.append(DigitalSetSnapshotEntry(
                state_code=int(code),
                state_name=s.get("nome", f"state_{int(code)}"),
                state_description=s.get("descricao"),
            ))
    entries.sort(key=lambda e: e.state_code)
    return tuple(entries)


def enrich_digital_result(
    base: DigitalAnalysisResult,
    recorded: list[AnalysisPoint],
    seed: AnalysisPoint | None,
    possible_states: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> DigitalAnalysisResult:
    """Deriva facts adicionais a partir de dados já calculados.

    NÃO chama PI. NÃO refaz a timeline inteira — reutiliza a classificação.
    Retorna DigitalAnalysisResult ampliado com campos enriquecidos.
    """
    state_code_map = _build_state_code_map(possible_states)
    state_ref_map = _build_state_ref_map(possible_states)
    window_seconds = (window_end - window_start).total_seconds()

    # Classificar eventos (seed + recorded)
    classified = _build_classified_events(seed, recorded, state_code_map, window_start, window_end)

    # Timeline segments com source
    timeline_segments = _build_timeline_segments(
        classified, seed, recorded, state_code_map, state_ref_map,
        window_start, window_end,
    )

    # Recorded events classificados
    classified_recorded = _build_classified_recorded_events(recorded, state_code_map, state_ref_map)

    # Seed info
    seed_info = _build_seed_info(seed, state_code_map, state_ref_map, window_start)

    # State statistics
    state_statistics = _build_state_statistics(timeline_segments, state_ref_map, window_seconds)

    # Transition statistics
    transition_statistics = _build_transition_statistics(timeline_segments, window_seconds)

    # Unknown value statistics
    unknown_stats = _build_unknown_value_statistics(timeline_segments, classified, window_seconds)

    # Quality summary
    quality_summary = _build_quality_summary(classified, timeline_segments, base.coverage, recorded, seed)

    # Daily summary (apenas >24h)
    daily_summary = _build_daily_summary(timeline_segments, base.transitions, window_start, window_end, window_seconds)

    # Digital set snapshot
    digital_set_snapshot = _build_digital_set_snapshot(possible_states)

    # Diagnostic warnings
    diagnostic_warnings = _build_diagnostic_warnings(base, seed_info, unknown_stats)

    return DigitalAnalysisResult(
        status=base.status,
        possible_states=base.possible_states,
        initial_state=base.initial_state,
        final_state=base.final_state,
        occupancy=base.occupancy,
        transitions=base.transitions,
        coverage=base.coverage,
        recorded_events_count=base.recorded_events_count,
        valid_events_count=base.valid_events_count,
        warnings=base.warnings,
        timeline_segments=timeline_segments,
        classified_recorded_events=classified_recorded,
        seed_info=seed_info,
        state_statistics=state_statistics,
        transition_statistics=transition_statistics,
        unknown_value_statistics=unknown_stats,
        quality_summary=quality_summary,
        daily_summary=daily_summary,
        digital_set_snapshot=digital_set_snapshot,
        diagnostic_warnings=diagnostic_warnings,
    )
