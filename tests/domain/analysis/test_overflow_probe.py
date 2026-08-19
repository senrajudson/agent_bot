from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from domain.analysis.models import AnalysisPoint, LimitStatus, AnalysisCompleteness
from domain.analysis.services.pi_data_collector import PiDataCollector, get_event_identity
from domain.core.config import configure_domain_settings
from domain.core.integration_settings import DomainIntegrationSettings


@pytest.fixture(autouse=True)
def setup_domain_settings():
    try:
        configure_domain_settings(DomainIntegrationSettings())
    except RuntimeError:
        pass


@pytest.mark.asyncio
async def test_event_identity_distinguishes_events() -> None:
    p1 = AnalysisPoint(timestamp="2026-08-15T12:00:00Z", value=10.0, good=True)
    p2 = AnalysisPoint(timestamp="2026-08-15T12:00:00Z", value=20.0, good=True)
    p3 = AnalysisPoint(timestamp="2026-08-15T12:00:00Z", value=10.0, good=False)
    
    assert get_event_identity(p1) != get_event_identity(p2)
    assert get_event_identity(p1) != get_event_identity(p3)
    assert get_event_identity(p1) == get_event_identity(AnalysisPoint(timestamp="2026-08-15T12:00:00Z", value=10.0, good=True))


@pytest.mark.asyncio
async def test_overflow_probe_not_reached() -> None:
    collector = PiDataCollector(recorded_max_count=5)
    mock_raw = {
        "Items": [
            {"Timestamp": f"2026-08-15T12:0{i}:00Z", "Value": i, "Good": True} for i in range(3)
        ]
    }
    with patch("domain.analysis.services.pi_data_collector.get_recorded_values_by_tag", AsyncMock(return_value=mock_raw)):
        points, meta, first_excluded = await collector._fetch_recorded_with_probe("TAG1", "2026-08-15T00:00:00Z", "2026-08-16T00:00:00Z")
        assert len(points) == 3
        assert meta.limit_status == LimitStatus.NOT_REACHED
        assert meta.analysis_completeness == AnalysisCompleteness.COMPLETE
        assert meta.truncated is False
        assert first_excluded is None


@pytest.mark.asyncio
async def test_overflow_probe_exceeded() -> None:
    collector = PiDataCollector(recorded_max_count=3)
    mock_main = {
        "Items": [
            {"Timestamp": f"2026-08-15T12:0{i}:00Z", "Value": i, "Good": True} for i in range(3)
        ]
    }
    mock_probe = {
        "Items": [
            {"Timestamp": "2026-08-15T12:02:00Z", "Value": 2, "Good": True},  # duplicata
            {"Timestamp": "2026-08-15T12:03:00Z", "Value": 3, "Good": True},  # novo evento
        ]
    }

    async def mock_get_recorded(tag, start, end, max_count):
        if max_count == 3:
            return mock_main
        return mock_probe

    with patch("domain.analysis.services.pi_data_collector.get_recorded_values_by_tag", AsyncMock(side_effect=mock_get_recorded)):
        points, meta, first_excluded = await collector._fetch_recorded_with_probe("TAG1", "2026-08-15T00:00:00Z", "2026-08-16T00:00:00Z")
        assert len(points) == 3
        assert meta.limit_status == LimitStatus.EXCEEDED
        assert meta.analysis_completeness == AnalysisCompleteness.PARTIAL
        assert meta.truncated is True
        assert first_excluded is not None
        assert first_excluded.value == 3
        assert first_excluded.timestamp == "2026-08-15T12:03:00Z"
