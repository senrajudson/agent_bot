from unittest.mock import AsyncMock, patch

import pytest

from domain.pims.clients.pi_point_resolver import (
    PiPointResolution,
    ResolutionStatus,
)


def _make_resolution(tag="T1", web_id="ABC123"):
    return PiPointResolution(
        status=ResolutionStatus.RESOLVED,
        tag=tag,
        items=({
            "WebId": web_id,
            "Name": tag,
            "Descriptor": "Test",
            "PointType": "Float32",
            "EngineeringUnits": "mm/s",
        },),
        transport_used="batch",
    )


@pytest.fixture(autouse=True)
def _configure_domain():
    from domain.core.config import _DOMAIN_CONFIG, configure_domain_settings
    from domain.core.integration_settings import DomainIntegrationSettings
    if _DOMAIN_CONFIG is None:
        configure_domain_settings(DomainIntegrationSettings(
            PI_WEB_API_BASE_URL="http://localhost:9999",
            PI_SERVER_NAME="PIMS",
            PI_WEB_API_USERNAME="",
            PI_WEB_API_PASSWORD="",
            PI_WEB_API_VERIFY_SSL=False,
        ))
    yield


@pytest.mark.asyncio
async def test_statistics_uses_resolver():
    from mcp_server.services.math_tool_service import executar_estatistica_tags_service

    mock_resolver = AsyncMock(return_value=_make_resolution())
    mock_buscar = AsyncMock(return_value={
        "tag": "T1",
        "method": "interpolated",
        "point_metadata": {"EngineeringUnits": "mm/s"},
        "raw_data": {"Items": []},
    })
    with patch(
        "mcp_server.services.math_tool_service.buscar_serie_pi",
        mock_buscar,
    ):
        result = await executar_estatistica_tags_service(
            tags=["T1"],
            operation="mean",
            start_time="2026-08-01",
            end_time="2026-08-02",
            resolver=mock_resolver,
        )
    assert "error" not in result or result.get("error") is None
    call_kwargs = mock_buscar.call_args
    assert call_kwargs.kwargs.get("resolver") is mock_resolver


@pytest.mark.asyncio
async def test_statistics_without_resolver():
    from mcp_server.services.math_tool_service import executar_estatistica_tags_service

    mock_buscar = AsyncMock(return_value={
        "tag": "T1",
        "method": "interpolated",
        "point_metadata": {"EngineeringUnits": "mm/s"},
        "raw_data": {"Items": []},
    })
    with patch(
        "mcp_server.services.math_tool_service.buscar_serie_pi",
        mock_buscar,
    ):
        result = await executar_estatistica_tags_service(
            tags=["T1"],
            operation="mean",
            start_time="2026-08-01",
            end_time="2026-08-02",
        )
    assert "error" not in result or result.get("error") is None
    call_kwargs = mock_buscar.call_args
    assert call_kwargs.kwargs.get("resolver") is None


@pytest.mark.asyncio
async def test_calculus_uses_resolver():
    from mcp_server.services.math_tool_service import executar_calculo_historico_service

    mock_resolver = AsyncMock(return_value=_make_resolution())
    mock_buscar = AsyncMock(return_value={
        "tag": "T1",
        "method": "interpolated",
        "point_metadata": {"EngineeringUnits": "mm/s"},
        "raw_data": {"Items": [
            {"Timestamp": "2026-08-01T00:00:00Z", "Value": 1.0},
            {"Timestamp": "2026-08-01T01:00:00Z", "Value": 2.0},
        ]},
    })
    with patch(
        "mcp_server.services.math_tool_service.buscar_serie_pi",
        mock_buscar,
    ), patch(
        "mcp_server.services.math_tool_service.call_calculus",
        AsyncMock(return_value={"result": 1.5}),
    ):
        result = await executar_calculo_historico_service(
            tags=["T1"],
            operation="integral",
            start_time="2026-08-01",
            end_time="2026-08-02",
            resolver=mock_resolver,
        )
    assert "error" not in result or result.get("error") is None
    call_kwargs = mock_buscar.call_args
    assert call_kwargs.kwargs.get("resolver") is mock_resolver
