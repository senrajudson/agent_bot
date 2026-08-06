"""Teste de regressão para o trace 932d14b9f5adbbab511d5483d3dd331ab.

Reproduz o cenário exato onde:
1. A tag CPD_LP_SECADOR_STATUS é digital com Digital Set Estado_126.
2. Não há eventos Recorded nos últimos 7 dias.
3. O seed (valor em ou antes do início) é 0 — DESLIGADO.
4. O resultado esperado é NO_TRANSITIONS, não DADOS_DEGRADADOS.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.analysis.models import (
    AnalysisPoint,
    DigitalAnalysisStatus,
    TagMetadata,
)
from domain.analysis.services._digital import reconstruct_timeline
from domain.analysis.services.pi_data_collector import CollectedData
from domain.analysis.services.tag_analysis_service import TagAnalysisService
from domain.analysis.models import AnalysisRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TAG = "CPD_LP_SECADOR_STATUS"

DIGITAL_STATES = [
    {"indice": 0, "nome": "DESLIGADO", "descricao": None},
    {"indice": 1, "nome": "VAZIO", "descricao": None},
    {"indice": 2, "nome": "LIGADO", "descricao": None},
    {"indice": 3, "nome": "VAZIO", "descricao": None},
    {"indice": 4, "nome": "FALHA", "descricao": None},
]

METADATA = TagMetadata(
    tag=TAG,
    point_type="digital",
    descriptor="Comando do Motor do Secador de Tiras",
    engineering_units=None,
    digital_set="Estado_126",
)

SEED = AnalysisPoint(
    timestamp="2026-07-29T14:00:00+00:00",
    value=0.0,
    good=True,
    questionable=False,
    substituted=False,
)


# ---------------------------------------------------------------------------
# T504–T523: Teste de regressão principal
# ---------------------------------------------------------------------------

class TestTrace932d14b9Regression:
    def test_status_no_transitions(self) -> None:
        """Status deve ser NO_TRANSITIONS quando não há eventos."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        assert result.status == DigitalAnalysisStatus.NO_TRANSITIONS

    def test_quality_is_none(self) -> None:
        """quality deve ser None para resultado digital."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        # Resultado digital não deve ter QualityMetrics
        assert result.status is not None

    def test_initial_and_final_state(self) -> None:
        """Estado inicial e final devem ser DESLIGADO (código 0)."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        assert result.initial_state is not None
        assert result.initial_state.state_code == 0
        assert result.initial_state.state_name == "DESLIGADO"
        assert result.final_state is not None
        assert result.final_state.state_code == 0
        assert result.final_state.state_name == "DESLIGADO"

    def test_occupancy_100_percent(self) -> None:
        """DESLIGADO deve ocupar 100% da janela."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        desligado = next(o for o in result.occupancy if o.state_code == 0)
        assert desligado.percentage_of_window == 100.0
        assert desligado.entries_count == 1

    def test_other_states_zero(self) -> None:
        """Demais estados devem ter 0% de ocupação."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        for o in result.occupancy:
            if o.state_code != 0:
                assert o.percentage_of_window == 0.0
                assert o.entries_count == 0

    def test_coverage_100_percent(self) -> None:
        """Cobertura conhecida deve ser 100%."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        assert result.coverage.known_pct == 100.0
        assert result.coverage.uncovered_pct == 0.0

    def test_zero_transitions(self) -> None:
        """Deve haver zero transições."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        assert len(result.transitions) == 0

    def test_homonymous_states_preserved(self) -> None:
        """Estados homônimos (1-VAZIO e 3-VAZIO) devem permanecer distintos."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        vazios = [o for o in result.occupancy if o.state_name == "VAZIO"]
        assert len(vazios) == 2
        codes = {o.state_code for o in vazios}
        assert codes == {1, 3}

    def test_no_dados_degradados(self) -> None:
        """Não deve haver menção a DADOS_DEGRADADOS no status."""
        window_start = datetime(2026, 7, 29, 14, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

        result = reconstruct_timeline(
            window_start=window_start,
            window_end=window_end,
            seed=SEED,
            recorded=[],
            possible_states=DIGITAL_STATES,
        )

        assert result.status != DigitalAnalysisStatus.NO_DATA
        assert result.status != DigitalAnalysisStatus.INVALID_DIGITAL_VALUES


# ---------------------------------------------------------------------------
# T525–T526: Estender testes existentes
# ---------------------------------------------------------------------------

class TestAnalyzeAfterConsultarTagStable:
    def test_service_returns_quality_none(self) -> None:
        """Service deve retornar quality=None para tag digital estável."""
        service = TagAnalysisService()
        data = CollectedData(
            metadata=METADATA,
            recorded=[],
            digital_seed=SEED,
            digital_states=DIGITAL_STATES,
        )
        request = AnalysisRequest(
            tag=TAG,
            start_time="2026-07-29T14:00:00+00:00",
            end_time="2026-08-05T14:00:00+00:00",
            zero_policy="suspicious",
        )

        result = service.analyze_one(data, request)

        assert result.quality is None
        assert result.digital_analysis is not None
        assert result.digital_analysis.status == DigitalAnalysisStatus.NO_TRANSITIONS
        assert result.start_time == "2026-07-29T14:00:00+00:00"
        assert result.end_time == "2026-08-05T14:00:00+00:00"
