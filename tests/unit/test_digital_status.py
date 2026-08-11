"""Testes de status digital — T056-T065.

Cobre: precedência dos 5 status e comportamento边界.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from domain.analysis.models import (
    AnalysisPoint,
    DigitalAnalysisStatus,
)
from domain.analysis.services._digital import reconstruct_timeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TZ = timezone(timedelta(hours=-3))

ESTADO_126 = [
    {"indice": 0, "nome": "DESLIGADO", "descricao": "Desligado"},
    {"indice": 1, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 2, "nome": "LIGADO", "descricao": "Ligado"},
    {"indice": 3, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 4, "nome": "FALHA", "descricao": "Falha"},
]


def _pt(s: str, v: float | None, good: bool = True) -> AnalysisPoint:
    return AnalysisPoint(timestamp=s, value=v, good=good)


def _seed(v: float, ts: str = "2026-08-01T00:00:00-03:00", good: bool = True) -> AnalysisPoint:
    return AnalysisPoint(timestamp=ts, value=v, good=good)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, 0, 0, tzinfo=_TZ)


# ---------------------------------------------------------------------------
# T056 — NO_DATA
# ---------------------------------------------------------------------------

class TestT056_NoData:
    def test_no_data(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=None,
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_DATA


# ---------------------------------------------------------------------------
# T057 — INVALID_DIGITAL_VALUES
# ---------------------------------------------------------------------------

class TestT057_InvalidDigitalValues:
    def test_invalid_digital_values(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[_pt("2026-08-01T12:00:00-03:00", 99.0)],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.INVALID_DIGITAL_VALUES
        assert result.coverage.known_seconds == 0


# ---------------------------------------------------------------------------
# T058 — PARTIAL_COVERAGE
# ---------------------------------------------------------------------------

class TestT058_PartialCoverage:
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


# ---------------------------------------------------------------------------
# T059 — NO_TRANSITIONS
# ---------------------------------------------------------------------------

class TestT059_NoTransitions:
    def test_no_transitions(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_TRANSITIONS
        assert len(result.transitions) == 0
        assert abs(result.coverage.known_pct - 100.0) < 0.1


# ---------------------------------------------------------------------------
# T060 — COMPLETE
# ---------------------------------------------------------------------------

class TestT060_Complete:
    def test_complete(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[_pt("2026-08-01T12:00:00-03:00", 2.0)],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.COMPLETE
        assert len(result.transitions) > 0
        assert abs(result.coverage.known_pct - 100.0) < 0.1


# ---------------------------------------------------------------------------
# T061 — Precedência NO_DATA sobre INVALID
# ---------------------------------------------------------------------------

class TestT061_PrecedenceNoData:
    def test_no_data_over_invalid(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=None,
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.NO_DATA
        assert result.status != DigitalAnalysisStatus.INVALID_DIGITAL_VALUES


# ---------------------------------------------------------------------------
# T062 — Precedência INVALID sobre PARTIAL
# ---------------------------------------------------------------------------

class TestT062_PrecedenceInvalid:
    def test_invalid_over_partial(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[_pt("2026-08-01T12:00:00-03:00", 99.0)],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.INVALID_DIGITAL_VALUES
        assert result.status != DigitalAnalysisStatus.PARTIAL_COVERAGE


# ---------------------------------------------------------------------------
# T063 — Precedência PARTIAL sobre NO_TRANSITIONS
# ---------------------------------------------------------------------------

class TestT063_PrecedencePartial:
    def test_partial_over_no_transitions(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[_pt("2026-08-01T12:00:00-03:00", 0.0)],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.PARTIAL_COVERAGE
        assert result.status != DigitalAnalysisStatus.NO_TRANSITIONS


# ---------------------------------------------------------------------------
# T064 — Eventos repetidos sem transição
# ---------------------------------------------------------------------------

class TestT064_RepetitionNoTransition:
    def test_repetition_no_transition(self) -> None:
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
        assert result.status == DigitalAnalysisStatus.NO_TRANSITIONS
        assert result.status != DigitalAnalysisStatus.COMPLETE


# ---------------------------------------------------------------------------
# T065 — Transição com cobertura total
# ---------------------------------------------------------------------------

class TestT065_CompleteWithCoverage:
    def test_complete_with_full_coverage(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T12:00:00-03:00", 2.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.status == DigitalAnalysisStatus.COMPLETE
        assert abs(result.coverage.known_pct - 100.0) < 0.1
        assert len(result.transitions) > 0
