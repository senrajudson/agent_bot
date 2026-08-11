"""Testes FastMCP digital — T119-T128.

Cobre: NO_TRANSITIONS, NO_DATA, PARTIAL_COVERAGE, INVALID_DIGITAL_VALUES,
Bad, Unknown, report multi-tag, sem recomendação operacional.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from domain.analysis.models import (
    AnalysisError,
    AnalysisPoint,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    DigitalCoverageMetrics,
    DigitalStateOccupancy,
    DigitalStateRef,
    TagMetadata,
)
from domain.analysis.services.pi_data_collector import CollectedData


METADATA_DIGITAL = TagMetadata(
    tag="CPD_LP_SECADOR_STATUS",
    point_type="digital",
    descriptor="Secador Status",
    digital_set="Estado_126",
)

STATES_126 = [
    {"indice": 0, "nome": "DESLIGADO", "descricao": "Desligado"},
    {"indice": 1, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 2, "nome": "LIGADO", "descricao": "Ligado"},
    {"indice": 3, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 4, "nome": "FALHA", "descricao": "Falha"},
]


def _digital_data(
    seed_value: float = 0.0,
    recorded: list[AnalysisPoint] | None = None,
    seed_good: bool = True,
) -> CollectedData:
    seed = AnalysisPoint(timestamp="2026-08-01T00:00:00-03:00", value=seed_value, good=seed_good)
    return CollectedData(
        metadata=METADATA_DIGITAL,
        recorded=recorded or [],
        digital_seed=seed,
        digital_initial="DESLIGADO",
        digital_states=STATES_126,
    )


# ---------------------------------------------------------------------------
# T119 — NO_TRANSITIONS via FastMCP
# ---------------------------------------------------------------------------

class TestT119_McpNoTransitions:
    def test_no_transitions(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = _digital_data(seed_value=0.0, recorded=[])
        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="CPD_LP_SECADOR_STATUS",
                start_time="*-7d",
                end_time="*",
            ))

        assert isinstance(result, str)
        assert "no_transitions" in result.lower() or "DESLIGADO" in result
        assert "DADOS_DEGRADADOS" not in result
        assert "good_pct=0%" not in result


# ---------------------------------------------------------------------------
# T120 — NO_DATA via FastMCP
# ---------------------------------------------------------------------------

class TestT120_McpNoData:
    def test_no_data(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = CollectedData(
            metadata=METADATA_DIGITAL,
            recorded=[],
            digital_seed=None,
            digital_states=STATES_126,
        )
        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="TAG",
                start_time="*-7d",
                end_time="*",
            ))

        assert isinstance(result, str)
        assert "no_data" in result.lower() or "nenhum" in result.lower()


# ---------------------------------------------------------------------------
# T121 — PARTIAL_COVERAGE via FastMCP
# ---------------------------------------------------------------------------

class TestT121_McpPartial:
    def test_partial_coverage(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = CollectedData(
            metadata=METADATA_DIGITAL,
            recorded=[AnalysisPoint(timestamp="2026-08-04T12:00:00-03:00", value=0.0)],
            digital_seed=None,
            digital_states=STATES_126,
        )
        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="TAG",
                start_time="*-7d",
                end_time="*",
            ))

        assert isinstance(result, str)
        assert "partial_coverage" in result.lower() or "parcial" in result.lower()


# ---------------------------------------------------------------------------
# T122 — INVALID_DIGITAL_VALUES via FastMCP
# ---------------------------------------------------------------------------

class TestT122_McpInvalid:
    def test_invalid_digital_values(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = CollectedData(
            metadata=METADATA_DIGITAL,
            recorded=[AnalysisPoint(timestamp="2026-08-04T12:00:00-03:00", value=99.0)],
            digital_seed=None,
            digital_states=STATES_126,
        )
        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="TAG",
                start_time="*-7d",
                end_time="*",
            ))

        assert isinstance(result, str)
        assert "invalid_digital_values" in result.lower() or "nenhum estado conhecido" in result.lower()


# ---------------------------------------------------------------------------
# T123 — Bad via FastMCP
# ---------------------------------------------------------------------------

class TestT123_McpBad:
    def test_bad_reported(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = _digital_data(seed_value=0.0, seed_good=False)
        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="TAG",
                start_time="*-7d",
                end_time="*",
            ))

        assert isinstance(result, str)
        assert "bad" in result.lower()
        assert "DADOS_DEGRADADOS" not in result


# ---------------------------------------------------------------------------
# T124 — Unknown via FastMCP
# ---------------------------------------------------------------------------

class TestT124_McpUnknown:
    def test_unknown_reported(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = CollectedData(
            metadata=METADATA_DIGITAL,
            recorded=[AnalysisPoint(timestamp="2026-08-04T12:00:00-03:00", value=99.0)],
            digital_seed=None,
            digital_states=STATES_126,
        )
        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="TAG",
                start_time="*-7d",
                end_time="*",
            ))

        assert isinstance(result, str)
        assert "desconhecido" in result.lower() or "unknown" in result.lower()


# ---------------------------------------------------------------------------
# T125 — Report multi-tag
# ---------------------------------------------------------------------------

class TestT125_McpMultiTag:
    def test_multi_tag(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report

        ok_digital = _digital_data(seed_value=0.0, recorded=[])
        ok_numeric = CollectedData(
            metadata=TagMetadata(tag="LFI_NUM", point_type="numeric", descriptor="Num", engineering_units="Nm3/h"),
            recorded=[AnalysisPoint(timestamp="2026-08-01T00:00:00-03:00", value=10.0)],
            interpolated=[AnalysisPoint(timestamp="2026-08-01T00:00:00-03:00", value=10.0)],
        )
        error = AnalysisError(tag="FAIL", code="PI_TIMEOUT", message="timeout", retryable=True)

        collected = {"DIG": ok_digital, "NUM": ok_numeric, "FAIL": error}

        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_many = AsyncMock(return_value=collected)
            result = asyncio.run(generate_pi_tags_analysis_report(
                tags=["DIG", "NUM", "FAIL"],
                start_time="*-7d",
                end_time="*",
            ))

        # Should return a string (ArtifactManifest or error message)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# T128 — Sem recomendação operacional
# ---------------------------------------------------------------------------

class TestT128_NoOperationalRecommendation:
    def test_no_recommendation(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = _digital_data(seed_value=0.0, recorded=[])
        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="TAG",
                start_time="*-7d",
                end_time="*",
            ))

        lower = result.lower()
        for term in ("manutenção", "trocar", "corrigir o pi", "intervenção", "equipamento"):
            assert term not in lower, f"Recomendação operacional '{term}' encontrada"
