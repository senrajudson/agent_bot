"""Testes de service digital — T081-T090.

Cobre: assess_quality não chamado, quality=None, digital_analysis,
campos legados, zero_policy, timestamps com offset, partial result.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest

from domain.analysis.models import (
    AnalysisError,
    AnalysisPoint,
    AnalysisRequest,
    DigitalAnalysisResult,
    DigitalAnalysisStatus,
    TagAnalysisResult,
    TagMetadata,
)
from domain.analysis.services.pi_data_collector import CollectedData
from domain.analysis.services.tag_analysis_service import TagAnalysisService


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


@pytest.fixture
def service() -> TagAnalysisService:
    return TagAnalysisService()


def _make_digital_data(
    seed_value: float = 0.0,
    recorded: list[AnalysisPoint] | None = None,
) -> CollectedData:
    seed = AnalysisPoint(timestamp="2026-08-01T00:00:00-03:00", value=seed_value)
    return CollectedData(
        metadata=METADATA_DIGITAL,
        recorded=recorded or [],
        digital_seed=seed,
        digital_initial="DESLIGADO",
        digital_states=STATES_126,
    )


# ---------------------------------------------------------------------------
# T081 — Digital não chama assess_quality
# ---------------------------------------------------------------------------

class TestT081_NoAssessQuality:
    def test_assess_quality_not_called(self, service: TagAnalysisService) -> None:
        data = _make_digital_data()
        req = AnalysisRequest(
            tag="CPD_LP_SECADOR_STATUS",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
        )
        with patch("domain.analysis.services.tag_analysis_service.assess_quality") as mock_aq:
            result = service.analyze_one(data, req)
            mock_aq.assert_not_called()


# ---------------------------------------------------------------------------
# T082 — quality=None
# ---------------------------------------------------------------------------

class TestT082_QualityNone:
    def test_quality_is_none(self, service: TagAnalysisService) -> None:
        data = _make_digital_data()
        req = AnalysisRequest(
            tag="TAG",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
        )
        result = service.analyze_one(data, req)
        assert result.quality is None


# ---------------------------------------------------------------------------
# T083 — digital_analysis preenchido
# ---------------------------------------------------------------------------

class TestT083_DigitalAnalysisFilled:
    def test_digital_analysis_present(self, service: TagAnalysisService) -> None:
        data = _make_digital_data()
        req = AnalysisRequest(
            tag="TAG",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
        )
        result = service.analyze_one(data, req)
        assert result.digital_analysis is not None
        assert isinstance(result.digital_analysis, DigitalAnalysisResult)


# ---------------------------------------------------------------------------
# T084 — Campos legados derivados
# ---------------------------------------------------------------------------

class TestT084_LegacyFields:
    def test_legacy_fields_present(self, service: TagAnalysisService) -> None:
        data = _make_digital_data()
        req = AnalysisRequest(
            tag="TAG",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
        )
        result = service.analyze_one(data, req)
        assert isinstance(result.digital_durations, tuple)
        assert isinstance(result.digital_transitions, tuple)


# ---------------------------------------------------------------------------
# T085 — Snapshot numérico preservado
# ---------------------------------------------------------------------------

class TestT085_NumericSnapshot:
    def test_numeric_unchanged(self, service: TagAnalysisService) -> None:
        data = CollectedData(
            metadata=TagMetadata(tag="LFI_TEST", point_type="numeric", descriptor="Test", engineering_units="Nm3/h"),
            recorded=[
                AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0),
                AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=20.0),
            ],
            interpolated=[
                AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0),
                AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=15.0),
            ],
        )
        req = AnalysisRequest(
            tag="LFI_TEST",
            start_time="2026-01-01T00:00:00-03:00",
            end_time="2026-01-01T01:00:00-03:00",
        )
        result = service.analyze_one(data, req)
        assert result.quality is not None
        assert result.quality.verdict == "DADOS_EXCELENTES"
        assert result.numeric is not None
        # recorded + interpolated = 4 points (service concatenates them)
        assert result.numeric.count == 4


# ---------------------------------------------------------------------------
# T086 — zero_policy digital
# ---------------------------------------------------------------------------

class TestT086_ZeroPolicyDigital:
    def test_zero_policy_ignored(self, service: TagAnalysisService) -> None:
        data = _make_digital_data()
        req = AnalysisRequest(
            tag="TAG",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
            zero_policy="invalid",
        )
        result = service.analyze_one(data, req)
        assert "zero_policy ignorado" in " ".join(result.warnings).lower()
        # Result should be identical regardless of zero_policy
        req_valid = AnalysisRequest(
            tag="TAG",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
            zero_policy="valid",
        )
        result_valid = service.analyze_one(data, req_valid)
        assert result.digital_analysis.status == result_valid.digital_analysis.status


# ---------------------------------------------------------------------------
# T088 — NO_DATA como sucesso
# ---------------------------------------------------------------------------

class TestT088_NoDataSuccess:
    def test_no_data_is_success(self, service: TagAnalysisService) -> None:
        data = CollectedData(
            metadata=METADATA_DIGITAL,
            recorded=[],
            digital_seed=None,
            digital_states=STATES_126,
        )
        req = AnalysisRequest(
            tag="TAG",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
        )
        result = service.analyze_one(data, req)
        assert isinstance(result, TagAnalysisResult)
        assert result.digital_analysis.status == DigitalAnalysisStatus.NO_DATA


# ---------------------------------------------------------------------------
# T089 — INVALID_DIGITAL_VALUES como sucesso
# ---------------------------------------------------------------------------

class TestT089_InvalidDigitalSuccess:
    def test_invalid_digital_is_success(self, service: TagAnalysisService) -> None:
        data = CollectedData(
            metadata=METADATA_DIGITAL,
            recorded=[AnalysisPoint(timestamp="2026-08-01T12:00:00-03:00", value=99.0)],
            digital_seed=None,
            digital_states=STATES_126,
        )
        req = AnalysisRequest(
            tag="TAG",
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-02T00:00:00-03:00",
        )
        result = service.analyze_one(data, req)
        assert isinstance(result, TagAnalysisResult)
        assert result.digital_analysis.status == DigitalAnalysisStatus.INVALID_DIGITAL_VALUES


# ---------------------------------------------------------------------------
# T090 — Partial result em analyze_many
# ---------------------------------------------------------------------------

class TestT090_PartialResult:
    def test_partial_success(self, service: TagAnalysisService) -> None:
        ok_data = _make_digital_data()
        error = AnalysisError(tag="FAIL", code="PI_TIMEOUT", message="timeout", retryable=True)
        collected = {"OK": ok_data, "FAIL": error}
        req = AnalysisRequest(
            start_time="2026-08-01T00:00:00-03:00",
            end_time="2026-08-08T00:00:00-03:00",
        )
        result = service.analyze_many(collected, req)
        assert result.total_processed == 1
        assert len(result.errors) == 1
        assert result.results[0].digital_analysis is not None
