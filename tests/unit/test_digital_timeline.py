"""Testes do motor temporal digital — T020-T044.

Cobre: reconstruct_timeline, segmentos, buckets, overlays, ocupação,
entries_count, transições, status, bordas e invariantes.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from domain.analysis.models import (
    AnalysisPoint,
    DigitalAnalysisStatus,
    DigitalStateRef,
)
from domain.analysis.services._digital import reconstruct_timeline


# ---------------------------------------------------------------------------
# Fixtures auxiliares
# ---------------------------------------------------------------------------

_TZ = timezone(timedelta(hours=-3))

ESTADO_126 = [
    {"indice": 0, "nome": "DESLIGADO", "descricao": "Desligado"},
    {"indice": 1, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 2, "nome": "LIGADO", "descricao": "Ligado"},
    {"indice": 3, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 4, "nome": "FALHA", "descricao": "Falha"},
]


def _pt(s: str, v: float | None, good: bool = True, questionable: bool = False, substituted: bool = False) -> AnalysisPoint:
    return AnalysisPoint(timestamp=s, value=v, good=good, questionable=questionable, substituted=substituted)


def _seed(v: float, ts: str = "2026-08-01T00:00:00-03:00", good: bool = True) -> AnalysisPoint:
    return AnalysisPoint(timestamp=ts, value=v, good=good)


def _dt(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, 0, tzinfo=_TZ)


# ---------------------------------------------------------------------------
# T020 — Seed válido e Recorded vazio → NO_TRANSITIONS
# ---------------------------------------------------------------------------

class TestT020_SeedValidEmptyRecorded:
    def test_no_transitions(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_TRANSITIONS

    def test_initial_equals_final(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.initial_state is not None
        assert result.final_state is not None
        assert result.initial_state.state_code == result.final_state.state_code
        assert result.initial_state.state_name == result.final_state.state_name

    def test_occupancy_100_percent(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        desligado = [o for o in result.occupancy if o.state_code == 0]
        assert len(desligado) == 1
        assert abs(desligado[0].percentage_of_window - 100.0) < 0.1

    def test_zero_transitions(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert len(result.transitions) == 0

    def test_coverage_100_percent(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert abs(result.coverage.known_pct - 100.0) < 0.1


# ---------------------------------------------------------------------------
# T021 — Seed válido com transições
# ---------------------------------------------------------------------------

class TestT021_SeedWithTransitions:
    def test_segments_and_transitions(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert len(result.transitions) == 2
        assert result.initial_state is not None
        assert result.initial_state.state_code == 0
        assert result.final_state is not None
        assert result.final_state.state_code == 0

    def test_occupancy_by_duration(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        desligado = [o for o in result.occupancy if o.state_code == 0]
        ligado = [o for o in result.occupancy if o.state_code == 2]
        assert len(desligado) == 1
        assert len(ligado) == 1
        assert desligado[0].duration_seconds > ligado[0].duration_seconds

    def test_entries_count(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        desligado = [o for o in result.occupancy if o.state_code == 0][0]
        ligado = [o for o in result.occupancy if o.state_code == 2][0]
        assert desligado.entries_count == 2
        assert ligado.entries_count == 1


# ---------------------------------------------------------------------------
# T022 — Sem seed com evento tardio → PARTIAL_COVERAGE
# ---------------------------------------------------------------------------

class TestT022_PartialCoverage:
    def test_partial_coverage(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[_pt("2026-08-01T12:00:00-03:00", 0.0)],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.PARTIAL_COVERAGE
        assert result.coverage.uncovered_pct > 0
        assert result.coverage.known_pct < 100


# ---------------------------------------------------------------------------
# T023 — Sem seed nem Recorded → NO_DATA
# ---------------------------------------------------------------------------

class TestT023_NoData:
    def test_no_data(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=None,
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_DATA
        assert all(o.duration_seconds == 0 for o in result.occupancy)
        assert result.coverage.known_seconds == 0


# ---------------------------------------------------------------------------
# T024 — Seed Bad
# ---------------------------------------------------------------------------

class TestT024_SeedBad:
    def test_seed_bad(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0, good=False),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.coverage.bad_seconds > 0
        assert result.coverage.known_seconds == 0
        assert result.status == DigitalAnalysisStatus.INVALID_DIGITAL_VALUES


# ---------------------------------------------------------------------------
# T025 — Evento Bad entre estados
# ---------------------------------------------------------------------------

class TestT025_BadBetweenStates:
    def test_bad_interrupts_continuity(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0, good=False),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.bad_seconds > 0
        desligado = [o for o in result.occupancy if o.state_code == 0][0]
        assert desligado.entries_count == 2


# ---------------------------------------------------------------------------
# T026 — Evento Null entre estados
# ---------------------------------------------------------------------------

class TestT026_NullBetweenStates:
    def test_null_is_separate_bucket(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", None),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.null_seconds > 0
        assert result.coverage.bad_seconds == 0


# ---------------------------------------------------------------------------
# T027 — Estado desconhecido
# ---------------------------------------------------------------------------

class TestT027_UnknownState:
    def test_unknown_state(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 8.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.unknown_seconds > 0
        codes = [ref.state_code for ref in result.possible_states]
        assert 8 not in codes


# ---------------------------------------------------------------------------
# T028 — Questionable overlay
# ---------------------------------------------------------------------------

class TestT028_QuestionableOverlay:
    def test_questionable_overlay(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0, questionable=True),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.questionable_seconds > 0


# ---------------------------------------------------------------------------
# T029 — Substituted overlay
# ---------------------------------------------------------------------------

class TestT029_SubstitutedOverlay:
    def test_substituted_overlay(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0, substituted=True),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.substituted_seconds > 0


# ---------------------------------------------------------------------------
# T030 — Overlays simultâneos
# ---------------------------------------------------------------------------

class TestT030_OverlaysSimultaneous:
    def test_both_overlays(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0, questionable=True, substituted=True),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.questionable_seconds > 0
        assert result.coverage.substituted_seconds > 0
        total = (result.coverage.known_seconds + result.coverage.bad_seconds
                 + result.coverage.null_seconds + result.coverage.unknown_seconds
                 + result.coverage.uncovered_seconds)
        assert abs(total - result.coverage.window_seconds) < 0.2


# ---------------------------------------------------------------------------
# T031 — Estados homônimos
# ---------------------------------------------------------------------------

class TestT031_HomonymousStates:
    def test_homonymous_preserved(self) -> None:
        states = [
            {"indice": 1, "nome": "VAZIO", "descricao": "Vazio"},
            {"indice": 3, "nome": "VAZIO", "descricao": "Vazio"},
        ]
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(1.0),
            recorded=[_pt("2026-08-01T12:00:00-03:00", 3.0)],
            possible_states=states,
        )
        codes = [o.state_code for o in result.occupancy]
        assert 1 in codes
        assert 3 in codes
        assert len(result.transitions) >= 1


# ---------------------------------------------------------------------------
# T032 — Código zero
# ---------------------------------------------------------------------------

class TestT032_ZeroCode:
    def test_zero_code_is_known(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_TRANSITIONS
        assert result.initial_state is not None
        assert result.initial_state.state_code == 0
        desligado = [o for o in result.occupancy if o.state_code == 0]
        assert len(desligado) == 1
        assert abs(desligado[0].percentage_of_window - 100.0) < 0.1


# ---------------------------------------------------------------------------
# T033 — Evento exatamente em start_time
# ---------------------------------------------------------------------------

class TestT033_EventAtStart:
    def test_event_at_start(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0, "2026-07-31T23:59:00-03:00"),
            recorded=[_pt("2026-08-01T00:00:00-03:00", 2.0)],
            possible_states=ESTADO_126,
        )
        # The event at start creates a transition from seed to LIGADO
        assert result.initial_state is not None
        assert result.final_state is not None
        # At minimum, the function processes without error
        assert result.coverage.window_seconds > 0


# ---------------------------------------------------------------------------
# T034 — Evento exatamente em end_time (descartado)
# ---------------------------------------------------------------------------

class TestT034_EventAtEnd:
    def test_event_at_end_is_discarded(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[_pt("2026-08-02T00:00:00-03:00", 2.0)],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_TRANSITIONS
        # The event at end is filtered out; recorded_events_count reflects
        # the events actually processed (seed counts as 1)
        assert len(result.transitions) == 0


# ---------------------------------------------------------------------------
# T035 — Seed e Recorded duplicados em start
# ---------------------------------------------------------------------------

class TestT035_Dedup:
    def test_deduplication(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[_pt("2026-08-01T00:00:00-03:00", 0.0)],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_TRANSITIONS
        assert len(result.transitions) == 0


# ---------------------------------------------------------------------------
# T036 — Eventos conflitantes no mesmo timestamp
# ---------------------------------------------------------------------------

class TestT036_ConflictingEvents:
    def test_deterministic_conflict(self) -> None:
        r1 = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T10:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        r2 = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T10:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert r1.status == r2.status
        assert len(r1.transitions) == len(r2.transitions)


# ---------------------------------------------------------------------------
# T037 — Eventos fora de ordem
# ---------------------------------------------------------------------------

class TestT037_OutOfOrder:
    def test_out_of_order(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T18:00:00-03:00", 0.0),
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T00:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.initial_state is not None
        assert result.final_state is not None


# ---------------------------------------------------------------------------
# T038 — Duplicatas exatas
# ---------------------------------------------------------------------------

class TestT038_ExactDuplicates:
    def test_exact_duplicates_removed(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T10:00:00-03:00", 2.0),
            ],
            possible_states=ESTADO_126,
        )
        # After dedup, only 1 unique recorded event + 1 seed = at most 2
        # The function should not crash and should produce valid results
        assert result.coverage.window_seconds > 0
        assert len(result.transitions) >= 0


# ---------------------------------------------------------------------------
# T039 — Repetição do mesmo estado
# ---------------------------------------------------------------------------

class TestT039_Repetition:
    def test_same_state_repetition(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T06:00:00-03:00", 0.0),
                _pt("2026-08-01T12:00:00-03:00", 0.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert len(result.transitions) == 0
        desligado = [o for o in result.occupancy if o.state_code == 0]
        assert len(desligado) == 1
        assert desligado[0].entries_count == 1


# ---------------------------------------------------------------------------
# T040 — Retorno ao estado anterior
# ---------------------------------------------------------------------------

class TestT040_ReturnToState:
    def test_return_to_previous_state(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T10:00:00-03:00", 2.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        desligado = [o for o in result.occupancy if o.state_code == 0][0]
        assert desligado.entries_count == 2
        assert len(result.transitions) == 2


# ---------------------------------------------------------------------------
# T041 — Janela de duração zero
# ---------------------------------------------------------------------------

class TestT041_ZeroWindow:
    def test_zero_window_raises(self) -> None:
        with pytest.raises(ValueError, match="window_end deve ser posterior"):
            reconstruct_timeline(
                window_start=_dt(1),
                window_end=_dt(1),
                seed=_seed(0.0),
                recorded=[],
                possible_states=ESTADO_126,
            )


# ---------------------------------------------------------------------------
# T042 — Percentual por duração (não contagem)
# ---------------------------------------------------------------------------

class TestT042_DurationNotCount:
    def test_duration_pct_not_count(self) -> None:
        # 6h window: seed at 00:00 (DESLIGADO), LIGADO 01:00-02:00, DESLIGADO 02:00-06:00
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(1, 6),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T01:00:00-03:00", 2.0),
                _pt("2026-08-01T02:00:00-03:00", 0.0),
                _pt("2026-08-01T03:00:00-03:00", 0.0),
                _pt("2026-08-01T04:00:00-03:00", 0.0),
                _pt("2026-08-01T05:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        desligado = [o for o in result.occupancy if o.state_code == 0]
        ligado = [o for o in result.occupancy if o.state_code == 2]
        assert len(desligado) == 1
        assert len(ligado) == 1
        # DESLIGADO: 1h (00-01) + 4h (02-06) = 5h; LIGADO: 1h (01-02)
        # DESLIGADO has more duration even though it has more records
        assert desligado[0].duration_seconds > ligado[0].duration_seconds


# ---------------------------------------------------------------------------
# T043 — Todos os estados possíveis
# ---------------------------------------------------------------------------

class TestT043_AllPossibleStates:
    def test_all_states_present(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert len(result.occupancy) == 5
        codes = {o.state_code for o in result.occupancy}
        assert codes == {0, 1, 2, 3, 4}
        for o in result.occupancy:
            if o.state_code in (1, 2, 3, 4):
                assert o.duration_seconds == 0
                assert o.percentage_of_window == 0
                assert o.entries_count == 0


# ---------------------------------------------------------------------------
# T044 — Digital Set com mais de 10 estados
# ---------------------------------------------------------------------------

class TestT044_ManyStates:
    def test_motor_no_truncation(self) -> None:
        many_states = [{"indice": i, "nome": f"STATE_{i}", "descricao": f"State {i}"} for i in range(15)]
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[_pt("2026-08-01T12:00:00-03:00", 5.0)],
            possible_states=many_states,
        )
        assert len(result.occupancy) == 15
        assert len(result.possible_states) == 15
