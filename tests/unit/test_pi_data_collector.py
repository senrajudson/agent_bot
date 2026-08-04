from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.analysis.models import AnalysisError
from domain.analysis.services.pi_data_collector import CollectedData, PiDataCollector


@pytest.fixture
def collector() -> PiDataCollector:
    return PiDataCollector(max_concurrency=2)


MOCK_POINT_RESPONSE = {
    "Items": [
        {
            "WebId": "P1",
            "Name": "LFI_TEST",
            "Descriptor": "Test Tag",
            "EngineeringUnits": "Nm3/h",
            "PointType": "Float32",
            "DigitalSet": None,
        }
    ]
}

MOCK_RECORDED_RESPONSE = {
    "Items": [
        {"Timestamp": "2026-01-01T00:00:00-03:00", "Value": 10.0, "Good": True, "Questionable": False, "Substituted": False},
        {"Timestamp": "2026-01-01T00:05:00-03:00", "Value": 20.0, "Good": True, "Questionable": False, "Substituted": False},
    ]
}

MOCK_INTERPOLATED_RESPONSE = {
    "Items": [
        {"Timestamp": "2026-01-01T00:00:00-03:00", "Value": 10.0, "Good": True, "Questionable": False, "Substituted": False},
        {"Timestamp": "2026-01-01T00:05:00-03:00", "Value": 15.0, "Good": True, "Questionable": False, "Substituted": False},
    ]
}


@pytest.mark.asyncio
async def test_fetch_one_numeric(collector: PiDataCollector) -> None:
    with patch("domain.analysis.services.pi_data_collector.get_point_by_tag", new_callable=AsyncMock, return_value=MOCK_POINT_RESPONSE), \
         patch("domain.analysis.services.pi_data_collector.get_recorded_values_by_tag", new_callable=AsyncMock, return_value=MOCK_RECORDED_RESPONSE), \
         patch("domain.analysis.services.pi_data_collector.get_interpolated_values_by_tag", new_callable=AsyncMock, return_value=MOCK_INTERPOLATED_RESPONSE):
        result = await collector.fetch_one("LFI_TEST", "2026-01-01T00:00:00-03:00", "2026-01-01T01:00:00-03:00")

    assert isinstance(result, CollectedData)
    assert result.metadata.tag == "LFI_TEST"
    assert result.metadata.point_type == "numeric"
    assert len(result.recorded) == 2
    assert len(result.interpolated) == 2


@pytest.mark.asyncio
async def test_fetch_one_tag_not_found(collector: PiDataCollector) -> None:
    with patch("domain.analysis.services.pi_data_collector.get_point_by_tag", new_callable=AsyncMock, return_value={"Items": []}):
        result = await collector.fetch_one("NONEXISTENT", "2026-01-01T00:00:00-03:00", "2026-01-01T01:00:00-03:00")

    assert isinstance(result, AnalysisError)
    assert result.code == "TAG_NOT_FOUND"


@pytest.mark.asyncio
async def test_fetch_one_pi_timeout(collector: PiDataCollector) -> None:
    with patch("domain.analysis.services.pi_data_collector.get_point_by_tag", new_callable=AsyncMock, side_effect=TimeoutError("connection timeout")):
        result = await collector.fetch_one("LFI_TEST", "2026-01-01T00:00:00-03:00", "2026-01-01T01:00:00-03:00")

    assert isinstance(result, AnalysisError)
    assert result.code == "PI_TIMEOUT"
    assert result.retryable is True


@pytest.mark.asyncio
async def test_fetch_one_pi_auth_error(collector: PiDataCollector) -> None:
    with patch("domain.analysis.services.pi_data_collector.get_point_by_tag", new_callable=AsyncMock, side_effect=Exception("401 Unauthorized")):
        result = await collector.fetch_one("LFI_TEST", "2026-01-01T00:00:00-03:00", "2026-01-01T01:00:00-03:00")

    assert isinstance(result, AnalysisError)
    assert result.code == "PI_AUTH_ERROR"


@pytest.mark.asyncio
async def test_fetch_many_concurrent(collector: PiDataCollector) -> None:
    with patch("domain.analysis.services.pi_data_collector.get_point_by_tag", new_callable=AsyncMock, return_value=MOCK_POINT_RESPONSE), \
         patch("domain.analysis.services.pi_data_collector.get_recorded_values_by_tag", new_callable=AsyncMock, return_value=MOCK_RECORDED_RESPONSE), \
         patch("domain.analysis.services.pi_data_collector.get_interpolated_values_by_tag", new_callable=AsyncMock, return_value=MOCK_INTERPOLATED_RESPONSE):
        results = await collector.fetch_many(["A", "B", "C"], "2026-01-01T00:00:00-03:00", "2026-01-01T01:00:00-03:00")

    assert len(results) == 3
    assert all(isinstance(r, CollectedData) for r in results.values())


@pytest.mark.asyncio
async def test_fetch_many_partial_failure(collector: PiDataCollector) -> None:
    call_count = 0

    async def mock_point(tag: str):
        nonlocal call_count
        call_count += 1
        if tag == "FAIL":
            raise Exception("timeout")
        return MOCK_POINT_RESPONSE

    with patch("domain.analysis.services.pi_data_collector.get_point_by_tag", side_effect=mock_point), \
         patch("domain.analysis.services.pi_data_collector.get_recorded_values_by_tag", new_callable=AsyncMock, return_value=MOCK_RECORDED_RESPONSE), \
         patch("domain.analysis.services.pi_data_collector.get_interpolated_values_by_tag", new_callable=AsyncMock, return_value=MOCK_INTERPOLATED_RESPONSE):
        results = await collector.fetch_many(["OK", "FAIL", "OK2"], "2026-01-01T00:00:00-03:00", "2026-01-01T01:00:00-03:00")

    assert isinstance(results["OK"], CollectedData)
    assert isinstance(results["FAIL"], AnalysisError)
    assert isinstance(results["OK2"], CollectedData)


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(collector: PiDataCollector) -> None:
    max_concurrent = 0
    current_concurrent = 0

    async def slow_point(tag: str):
        nonlocal max_concurrent, current_concurrent
        current_concurrent += 1
        max_concurrent = max(max_concurrent, current_concurrent)
        await asyncio.sleep(0.01)
        current_concurrent -= 1
        return MOCK_POINT_RESPONSE

    import asyncio
    with patch("domain.analysis.services.pi_data_collector.get_point_by_tag", side_effect=slow_point), \
         patch("domain.analysis.services.pi_data_collector.get_recorded_values_by_tag", new_callable=AsyncMock, return_value=MOCK_RECORDED_RESPONSE), \
         patch("domain.analysis.services.pi_data_collector.get_interpolated_values_by_tag", new_callable=AsyncMock, return_value=MOCK_INTERPOLATED_RESPONSE):
        await collector.fetch_many([f"TAG_{i}" for i in range(10)], "2026-01-01T00:00:00-03:00", "2026-01-01T01:00:00-03:00")

    assert max_concurrent <= 2
