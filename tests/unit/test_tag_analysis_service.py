from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.analysis.models import (
    AnalysisError,
    AnalysisPoint,
    AnalysisRequest,
    TagAnalysisResult,
    TagMetadata,
    MultiTagAnalysisResult,
)
from domain.analysis.services.pi_data_collector import CollectedData
from domain.analysis.services.tag_analysis_service import TagAnalysisService
from domain.shared.errors import DomainValidationError


@pytest.fixture
def service() -> TagAnalysisService:
    return TagAnalysisService()


MOCK_METADATA_NUMERIC = TagMetadata(
    tag="LFI_TEST",
    point_type="numeric",
    descriptor="Test",
    engineering_units="Nm3/h",
    digital_set=None,
)

MOCK_METADATA_DIGITAL = TagMetadata(
    tag="ACI_VALVE",
    point_type="digital",
    descriptor="Valve",
    engineering_units=None,
    digital_set="ValveStates",
)

MOCK_COLLECTED_NUMERIC = CollectedData(
    metadata=MOCK_METADATA_NUMERIC,  # type: ignore[arg-type]
    recorded=[
        {"timestamp": "2026-01-01T00:00:00-03:00", "value": 10.0, "good": True, "questionable": False, "substituted": False},
        {"timestamp": "2026-01-01T00:05:00-03:00", "value": 20.0, "good": True, "questionable": False, "substituted": False},
    ],
    interpolated=[
        {"timestamp": "2026-01-01T00:00:00-03:00", "value": 10.0, "good": True, "questionable": False, "substituted": False},
        {"timestamp": "2026-01-01T00:05:00-03:00", "value": 15.0, "good": True, "questionable": False, "substituted": False},
    ],
)


class TestValidateRequest:
    def test_missing_tag_raises(self, service: TagAnalysisService) -> None:
        req = AnalysisRequest(start_time="2026-01-01T00:00:00-03:00", end_time="2026-01-02T00:00:00-03:00")
        with pytest.raises(DomainValidationError):
            service.validate_request(req)

    def test_valid_request(self, service: TagAnalysisService) -> None:
        req = AnalysisRequest(
            tag="LFI_TEST",
            start_time="2026-01-01T00:00:00-03:00",
            end_time="2026-01-02T00:00:00-03:00",
        )
        service.validate_request(req)

    def test_extras_rejected(self, service: TagAnalysisService) -> None:
        from domain.analysis.models import AnalysisRequest as AR
        with pytest.raises(TypeError):
            AR(tag="X", start_time="a", end_time="b", extra="nope")  # type: ignore[arg-type]


class TestAnalyzeOne:
    def test_numeric(self, service: TagAnalysisService) -> None:
        data = CollectedData(
            metadata=MOCK_METADATA_NUMERIC,  # type: ignore[arg-type]
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
        assert isinstance(result, TagAnalysisResult)
        assert result.metadata.tag == "LFI_TEST"
        assert result.numeric is not None
        assert result.numeric.count > 0

    def test_digital(self, service: TagAnalysisService) -> None:
        data = CollectedData(
            metadata=MOCK_METADATA_DIGITAL,  # type: ignore[arg-type]
            recorded=[
                AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=0.0),
                AnalysisPoint(timestamp="2026-01-01T01:00:00-03:00", value=1.0),
                AnalysisPoint(timestamp="2026-01-01T02:00:00-03:00", value=0.0),
            ],
            digital_initial="CLOSED",
            digital_states=[
                {"indice": 0, "nome": "CLOSED", "descricao": "Closed"},
                {"indice": 1, "nome": "OPEN", "descricao": "Open"},
            ],
        )
        req = AnalysisRequest(
            tag="ACI_VALVE",
            start_time="2026-01-01T00:00:00-03:00",
            end_time="2026-01-01T03:00:00-03:00",
        )
        result = service.analyze_one(data, req)
        assert isinstance(result, TagAnalysisResult)
        assert result.metadata.point_type == "digital"
        assert len(result.digital_durations) > 0
        assert len(result.digital_transitions) > 0


class TestAnalyzeMany:
    def test_partial_failure(self, service: TagAnalysisService) -> None:
        ok_data = CollectedData(
            metadata=MOCK_METADATA_NUMERIC,  # type: ignore[arg-type]
            recorded=[AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0)],
            interpolated=[AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0)],
        )
        error = AnalysisError(tag="FAIL", code="PI_TIMEOUT", message="timeout", retryable=True)

        collected = {"OK1": ok_data, "FAIL": error, "OK2": ok_data}
        req = AnalysisRequest(
            start_time="2026-01-01T00:00:00-03:00",
            end_time="2026-01-01T01:00:00-03:00",
        )
        result = service.analyze_many(collected, req)
        assert isinstance(result, MultiTagAnalysisResult)
        assert result.total_processed == 2
        assert len(result.errors) == 1
        assert result.errors[0].code == "PI_TIMEOUT"

    def test_all_failed(self, service: TagAnalysisService) -> None:
        collected = {
            "FAIL1": AnalysisError(tag="FAIL1", code="PI_TIMEOUT", message="t1", retryable=True),
            "FAIL2": AnalysisError(tag="FAIL2", code="TAG_NOT_FOUND", message="t2", retryable=False),
        }
        req = AnalysisRequest(
            start_time="2026-01-01T00:00:00-03:00",
            end_time="2026-01-01T01:00:00-03:00",
        )
        result = service.analyze_many(collected, req)
        assert result.total_processed == 0
        assert len(result.errors) == 2
