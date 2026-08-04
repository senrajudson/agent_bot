from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.analysis.models import AnalysisError
from domain.analysis.services.pi_data_collector import PiDataCollector
from domain.pims.clients.pi_point_resolver import (
    PiPointResolution,
    ResolutionStatus,
)


def _make_resolution(status, tag="T1", items=(), error_message_safe=None):
    return PiPointResolution(
        status=status,
        tag=tag,
        items=items,
        error_message_safe=error_message_safe,
    )


@pytest.mark.asyncio
async def test_resolver_resolved():
    resolution = _make_resolution(
        ResolutionStatus.RESOLVED,
        items=({
            "WebId": "A1",
            "Name": "T1",
            "Descriptor": "Test",
            "PointType": "Float32",
            "EngineeringUnits": "mm/s",
        },),
    )
    mock_resolver = AsyncMock(return_value=resolution)
    collector = PiDataCollector(resolver=mock_resolver)
    result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
    assert not isinstance(result, AnalysisError)
    assert result.metadata.tag == "T1"


@pytest.mark.asyncio
async def test_resolver_empty_result():
    resolution = _make_resolution(ResolutionStatus.EMPTY_RESULT)
    mock_resolver = AsyncMock(return_value=resolution)
    collector = PiDataCollector(resolver=mock_resolver)
    result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
    assert isinstance(result, AnalysisError)
    assert result.code == "EMPTY_RESULT"
    assert result.retryable is True


@pytest.mark.asyncio
async def test_resolver_not_found():
    resolution = _make_resolution(ResolutionStatus.NOT_FOUND)
    mock_resolver = AsyncMock(return_value=resolution)
    collector = PiDataCollector(resolver=mock_resolver)
    result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
    assert isinstance(result, AnalysisError)
    assert result.code == "TAG_NOT_FOUND"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_resolver_invalid_response():
    resolution = _make_resolution(ResolutionStatus.INVALID_RESPONSE)
    mock_resolver = AsyncMock(return_value=resolution)
    collector = PiDataCollector(resolver=mock_resolver)
    result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
    assert isinstance(result, AnalysisError)
    assert result.code == "INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_resolver_transport_error():
    resolution = _make_resolution(ResolutionStatus.TRANSPORT_ERROR)
    mock_resolver = AsyncMock(return_value=resolution)
    collector = PiDataCollector(resolver=mock_resolver)
    result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
    assert isinstance(result, AnalysisError)
    assert result.code == "PI_TRANSPORT_ERROR"
    assert result.retryable is True


@pytest.mark.asyncio
async def test_resolver_auth_error():
    resolution = _make_resolution(ResolutionStatus.AUTH_ERROR)
    mock_resolver = AsyncMock(return_value=resolution)
    collector = PiDataCollector(resolver=mock_resolver)
    result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
    assert isinstance(result, AnalysisError)
    assert result.code == "PI_AUTH_ERROR"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_tag_not_found_only_for_not_found():
    for status in [
        ResolutionStatus.EMPTY_RESULT,
        ResolutionStatus.INVALID_RESPONSE,
        ResolutionStatus.TRANSPORT_ERROR,
        ResolutionStatus.AUTH_ERROR,
        ResolutionStatus.AMBIGUOUS_RESOLUTION,
    ]:
        resolution = _make_resolution(status)
        mock_resolver = AsyncMock(return_value=resolution)
        collector = PiDataCollector(resolver=mock_resolver)
        result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
        assert isinstance(result, AnalysisError)
        assert result.code != "TAG_NOT_FOUND", f"Status {status} should not map to TAG_NOT_FOUND"


@pytest.mark.asyncio
async def test_legacy_path_without_resolver():
    mock_get_point = AsyncMock(return_value={
        "Items": [{
            "WebId": "A1",
            "Name": "T1",
            "Descriptor": "Test",
            "PointType": "Float32",
            "EngineeringUnits": "mm/s",
        }]
    })
    collector = PiDataCollector()
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "domain.analysis.services.pi_data_collector.get_point_by_tag",
            mock_get_point,
        )
        m.setattr(
            "domain.analysis.services.pi_data_collector.get_recorded_values_by_tag",
            AsyncMock(return_value={"Items": []}),
        )
        m.setattr(
            "domain.analysis.services.pi_data_collector.get_interpolated_values_by_tag",
            AsyncMock(return_value={"Items": []}),
        )
        result = await collector.fetch_one("T1", "2026-08-01", "2026-08-02")
    assert not isinstance(result, AnalysisError)
