from unittest.mock import AsyncMock

import pytest

from domain.pims.clients.pi_point_resolver import (
    PiPointResolution,
    ResolutionStatus,
    resolve_pi_point,
    resolve_pi_points,
)


@pytest.mark.asyncio
async def test_resolved_with_webid():
    batch_response = {
        "point_0": {
            "Status": 200,
            "Content": {
                "WebId": "ABC123",
                "Name": "T1",
                "Descriptor": "Test",
                "PointType": "Float32",
                "EngineeringUnits": "mm/s",
            },
        }
    }
    mock_batch = AsyncMock(return_value=batch_response)
    result = await resolve_pi_point("T1", batch_fn=mock_batch)
    assert result.status == ResolutionStatus.RESOLVED
    assert result.is_resolved is True
    assert result.tag == "T1"
    assert result.transport_used == "batch"
    assert result.http_status == 200
    assert len(result.items) == 1
    assert result.items[0]["WebId"] == "ABC123"


@pytest.mark.asyncio
async def test_empty_result():
    batch_response = {
        "point_0": {
            "Status": 200,
            "Content": {},
        }
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock(return_value={})
    result = await resolve_pi_point("T1", batch_fn=mock_batch, get_fn=mock_get)
    assert result.status == ResolutionStatus.EMPTY_RESULT
    assert result.is_resolved is False


@pytest.mark.asyncio
async def test_http_404():
    batch_response = {
        "point_0": {
            "Status": 404,
            "Content": {},
        }
    }
    mock_batch = AsyncMock(return_value=batch_response)
    result = await resolve_pi_point("T1", batch_fn=mock_batch)
    assert result.status == ResolutionStatus.NOT_FOUND
    assert result.http_status == 404


@pytest.mark.asyncio
async def test_http_401():
    batch_response = {
        "point_0": {
            "Status": 401,
            "Content": {},
        }
    }
    mock_batch = AsyncMock(return_value=batch_response)
    result = await resolve_pi_point("T1", batch_fn=mock_batch)
    assert result.status == ResolutionStatus.AUTH_ERROR
    assert result.http_status == 401


@pytest.mark.asyncio
async def test_http_500():
    batch_response = {
        "point_0": {
            "Status": 500,
            "Content": {},
        }
    }
    mock_batch = AsyncMock(return_value=batch_response)
    result = await resolve_pi_point("T1", batch_fn=mock_batch)
    assert result.status == ResolutionStatus.TRANSPORT_ERROR
    assert result.http_status == 500


@pytest.mark.asyncio
async def test_network_exception():
    mock_batch = AsyncMock(side_effect=ConnectionError("connection refused"))
    result = await resolve_pi_point("T1", batch_fn=mock_batch)
    assert result.status == ResolutionStatus.TRANSPORT_ERROR
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_timeout_exception():
    mock_batch = AsyncMock(side_effect=TimeoutError("timeout"))
    result = await resolve_pi_point("T1", batch_fn=mock_batch)
    assert result.status == ResolutionStatus.TRANSPORT_ERROR


@pytest.mark.asyncio
async def test_auth_exception():
    mock_batch = AsyncMock(side_effect=Exception("401 Unauthorized"))
    result = await resolve_pi_point("T1", batch_fn=mock_batch)
    assert result.status == ResolutionStatus.AUTH_ERROR


@pytest.mark.asyncio
async def test_empty_tag():
    result = await resolve_pi_point("", batch_fn=AsyncMock())
    assert result.status == ResolutionStatus.INVALID_RESPONSE
    assert result.error_code == "EMPTY_TAG"


@pytest.mark.asyncio
async def test_whitespace_tag():
    result = await resolve_pi_point("   ", batch_fn=AsyncMock())
    assert result.status == ResolutionStatus.INVALID_RESPONSE
    assert result.error_code == "EMPTY_TAG"


@pytest.mark.asyncio
async def test_fallback_dispatches_only_on_empty():
    batch_response = {
        "point_0": {"Status": 200, "Content": {}}
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock(return_value={"WebId": "ABC", "Name": "T1"})
    result = await resolve_pi_point("T1", batch_fn=mock_batch, get_fn=mock_get)
    assert result.status == ResolutionStatus.RESOLVED
    assert result.transport_used == "fallback"
    mock_get.assert_awaited_once_with("T1")


@pytest.mark.asyncio
async def test_primary_resolved_no_fallback():
    batch_response = {
        "point_0": {
            "Status": 200,
            "Content": {"WebId": "ABC", "Name": "T1"},
        }
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock()
    result = await resolve_pi_point("T1", batch_fn=mock_batch, get_fn=mock_get)
    assert result.status == ResolutionStatus.RESOLVED
    assert result.transport_used == "batch"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_resolution():
    batch_response = {
        "point_0": {"Status": 200, "Content": {}}
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock(return_value={})
    result = await resolve_pi_point("T1", batch_fn=mock_batch, get_fn=mock_get)
    assert result.status == ResolutionStatus.EMPTY_RESULT


@pytest.mark.asyncio
async def test_fallback_exception_returns_error():
    batch_response = {
        "point_0": {"Status": 200, "Content": {}}
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock(side_effect=ConnectionError("refused"))
    result = await resolve_pi_point("T1", batch_fn=mock_batch, get_fn=mock_get)
    assert result.status == ResolutionStatus.TRANSPORT_ERROR


@pytest.mark.asyncio
async def test_batch_http_404_no_fallback():
    batch_response = {
        "point_0": {"Status": 404, "Content": {}}
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock()
    result = await resolve_pi_point("T1", batch_fn=mock_batch, get_fn=mock_get)
    assert result.status == ResolutionStatus.NOT_FOUND
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_tag_all_resolved():
    batch_response = {
        "point_0": {"Status": 200, "Content": {"WebId": "A1", "Name": "T1"}},
        "point_1": {"Status": 200, "Content": {"WebId": "A2", "Name": "T2"}},
    }
    mock_batch = AsyncMock(return_value=batch_response)
    results = await resolve_pi_points(["T1", "T2"], batch_fn=mock_batch)
    assert len(results) == 2
    assert results[0].status == ResolutionStatus.RESOLVED
    assert results[1].status == ResolutionStatus.RESOLVED


@pytest.mark.asyncio
async def test_multi_tag_partial_failure():
    batch_response = {
        "point_0": {"Status": 200, "Content": {"WebId": "A1", "Name": "T1"}},
        "point_1": {"Status": 404, "Content": {}},
    }
    mock_batch = AsyncMock(return_value=batch_response)
    results = await resolve_pi_points(["T1", "T2"], batch_fn=mock_batch)
    assert len(results) == 2
    assert results[0].status == ResolutionStatus.RESOLVED
    assert results[1].status == ResolutionStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_multi_tag_empty_with_fallback():
    batch_response = {
        "point_0": {"Status": 200, "Content": {"WebId": "A1", "Name": "T1"}},
        "point_1": {"Status": 200, "Content": {}},
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock(return_value={"WebId": "A2", "Name": "T2"})
    results = await resolve_pi_points(
        ["T1", "T2"], batch_fn=mock_batch, get_fn=mock_get
    )
    assert len(results) == 2
    assert results[0].status == ResolutionStatus.RESOLVED
    assert results[1].status == ResolutionStatus.RESOLVED
    assert results[1].transport_used == "fallback"


@pytest.mark.asyncio
async def test_multi_tag_all_empty():
    batch_response = {
        "point_0": {"Status": 200, "Content": {}},
        "point_1": {"Status": 200, "Content": {}},
    }
    mock_batch = AsyncMock(return_value=batch_response)
    mock_get = AsyncMock(return_value={})
    results = await resolve_pi_points(
        ["T1", "T2"], batch_fn=mock_batch, get_fn=mock_get
    )
    assert len(results) == 2
    assert results[0].status == ResolutionStatus.EMPTY_RESULT
    assert results[1].status == ResolutionStatus.EMPTY_RESULT


@pytest.mark.asyncio
async def test_multi_tag_empty_list():
    results = await resolve_pi_points([], batch_fn=AsyncMock())
    assert results == []
