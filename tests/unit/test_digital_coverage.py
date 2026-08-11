"""Testes de cobertura e invariantes digitais — T045-T055.

Cobre: fechamento da partição, percentuais, tolerância, overlays,
janelas totalmente Bad/Null/Unknown/Uncovered, cobertura parcial combinada.
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


def _pt(s: str, v: float | None, good: bool = True, questionable: bool = False, substituted: bool = False) -> AnalysisPoint:
    return AnalysisPoint(timestamp=s, value=v, good=good, questionable=questionable, substituted=substituted)


def _seed(v: float, ts: str = "2026-08-01T00:00:00-03:00", good: bool = True) -> AnalysisPoint:
    return AnalysisPoint(timestamp=ts, value=v, good=good)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, 0, 0, tzinfo=_TZ)


# ---------------------------------------------------------------------------
# T045 — Fechamento da partição em segundos
# ---------------------------------------------------------------------------

class TestT045_PartitionCloses:
    def test_partition_closes(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T06:00:00-03:00", 2.0),
                _pt("2026-08-01T08:00:00-03:00", None),
                _pt("2026-08-01T10:00:00-03:00", 2.0, good=False),
                _pt("2026-08-01T12:00:00-03:00", 8.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        total = (result.coverage.known_seconds + result.coverage.bad_seconds
                 + result.coverage.null_seconds + result.coverage.unknown_seconds
                 + result.coverage.uncovered_seconds)
        assert abs(total - result.coverage.window_seconds) < 0.2


# ---------------------------------------------------------------------------
# T046 — Percentual total da partição
# ---------------------------------------------------------------------------

class TestT046_PercentageTotal:
    def test_pct_sums_to_100(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0),
            recorded=[
                _pt("2026-08-01T06:00:00-03:00", 2.0),
                _pt("2026-08-01T08:00:00-03:00", None),
                _pt("2026-08-01T10:00:00-03:00", 2.0, good=False),
                _pt("2026-08-01T12:00:00-03:00", 8.0),
                _pt("2026-08-01T18:00:00-03:00", 0.0),
            ],
            possible_states=ESTADO_126,
        )
        total_pct = (result.coverage.known_pct + result.coverage.bad_pct
                     + result.coverage.null_pct + result.coverage.unknown_pct
                     + result.coverage.uncovered_pct)
        assert abs(total_pct - 100.0) < 1.0


# ---------------------------------------------------------------------------
# T047 — Tolerância temporal
# ---------------------------------------------------------------------------

class TestT047_Tolerance:
    def test_within_tolerance_no_warning(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(8),
            seed=_seed(0.0),
            recorded=[],
            possible_states=ESTADO_126,
        )
        total = (result.coverage.known_seconds + result.coverage.bad_seconds
                 + result.coverage.null_seconds + result.coverage.unknown_seconds
                 + result.coverage.uncovered_seconds)
        assert abs(total - result.coverage.window_seconds) < 0.2


# ---------------------------------------------------------------------------
# T048 — Questionable como overlay
# ---------------------------------------------------------------------------

class TestT048_QuestionableOverlay:
    def test_questionable_does_not_affect_partition(self) -> None:
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
        total = (result.coverage.known_seconds + result.coverage.bad_seconds
                 + result.coverage.null_seconds + result.coverage.unknown_seconds
                 + result.coverage.uncovered_seconds)
        assert abs(total - result.coverage.window_seconds) < 0.2
        assert result.coverage.questionable_seconds > 0


# ---------------------------------------------------------------------------
# T049 — Substituted como overlay
# ---------------------------------------------------------------------------

class TestT049_SubstitutedOverlay:
    def test_substituted_does_not_affect_partition(self) -> None:
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
        total = (result.coverage.known_seconds + result.coverage.bad_seconds
                 + result.coverage.null_seconds + result.coverage.unknown_seconds
                 + result.coverage.uncovered_seconds)
        assert abs(total - result.coverage.window_seconds) < 0.2
        assert result.coverage.substituted_seconds > 0


# ---------------------------------------------------------------------------
# T050 — Overlays simultâneos
# ---------------------------------------------------------------------------

class TestT050_SimultaneousOverlays:
    def test_both_overlays_coexist(self) -> None:
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
# T051 — Janela totalmente Bad
# ---------------------------------------------------------------------------

class TestT051_AllBad:
    def test_all_bad(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=_seed(0.0, good=False),
            recorded=[_pt("2026-08-01T12:00:00-03:00", 2.0, good=False)],
            possible_states=ESTADO_126,
        )
        assert result.coverage.known_seconds == 0
        assert result.coverage.bad_pct > 90
        assert result.status == DigitalAnalysisStatus.INVALID_DIGITAL_VALUES


# ---------------------------------------------------------------------------
# T052 — Janela totalmente Null
# ---------------------------------------------------------------------------

class TestT052_AllNull:
    def test_all_null(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[
                _pt("2026-08-01T00:00:01-03:00", None),  # near start
            ],
            possible_states=ESTADO_126,
        )
        # Null event covers from its timestamp to window_end
        assert result.coverage.null_seconds > 0
        assert result.coverage.known_seconds == 0
        assert result.status == DigitalAnalysisStatus.INVALID_DIGITAL_VALUES


# ---------------------------------------------------------------------------
# T053 — Janela totalmente Unknown
# ---------------------------------------------------------------------------

class TestT053_AllUnknown:
    def test_all_unknown(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[
                _pt("2026-08-01T00:00:01-03:00", 99.0),  # near start
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.unknown_seconds > 0
        assert result.coverage.known_seconds == 0
        assert result.status == DigitalAnalysisStatus.INVALID_DIGITAL_VALUES


# ---------------------------------------------------------------------------
# T054 — Janela totalmente Uncovered
# ---------------------------------------------------------------------------

class TestT054_AllUncovered:
    def test_all_uncovered_is_no_data(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[],
            possible_states=ESTADO_126,
        )
        assert result.coverage.uncovered_pct == 100.0
        assert result.status == DigitalAnalysisStatus.NO_DATA


# ---------------------------------------------------------------------------
# T055 — Cobertura parcial combinada
# ---------------------------------------------------------------------------

class TestT055_PartialCombined:
    def test_partial_combined(self) -> None:
        result = reconstruct_timeline(
            window_start=_dt(1),
            window_end=_dt(2),
            seed=None,
            recorded=[
                _pt("2026-08-01T12:00:00-03:00", 0.0),
                _pt("2026-08-01T18:00:00-03:00", 99.0),
            ],
            possible_states=ESTADO_126,
        )
        assert result.coverage.known_seconds > 0
        assert result.coverage.uncovered_seconds > 0
        assert result.coverage.unknown_seconds > 0
        assert result.status == DigitalAnalysisStatus.PARTIAL_COVERAGE
        total = (result.coverage.known_seconds + result.coverage.bad_seconds
                 + result.coverage.null_seconds + result.coverage.unknown_seconds
                 + result.coverage.uncovered_seconds)
        assert abs(total - result.coverage.window_seconds) < 0.2
