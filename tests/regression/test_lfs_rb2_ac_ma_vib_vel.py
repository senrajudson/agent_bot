"""Teste de regressão do trace d4bc9b77d2c4a543b5d30c2efd62b92f.

Reproduz o cenário exato onde:
1. consultar_tag encontrou a tag via POST /batch
2. analyze_pi_tag_behavior retornou TAG_NOT_FOUND via GET direto

Com o resolver canônico, analyze_pi_tag_behavior deve retornar sucesso.
"""
from unittest.mock import AsyncMock, patch

import pytest

from domain.pims.clients.pi_point_resolver import (
    PiPointResolution,
    ResolutionStatus,
)
from domain.analysis.services.pi_data_collector import PiDataCollector


TAG = "LFS_RB2_AC_MA_VIB_VEL"
WEB_ID = "F1DPxhF1MCtATE6DjgaMSVY2gg6oQBAAUElNU1xMRlNfUkIyX0FDX01BX1ZJQl9WRUw"


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


def _batch_response_resolved():
    return {
        "point_0": {
            "Status": 200,
            "Content": {
                "WebId": WEB_ID,
                "Name": TAG,
                "Descriptor": "VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
                "PointType": "Float32",
                "EngineeringUnits": "mm/s",
            },
        }
    }


def _get_response_not_found():
    return {}


@pytest.mark.asyncio
async def test_trace_d4bc9b77_regression():
    """Com resolver canônico, a tag LFS_RB2_AC_MA_VIB_VEL deve ser encontrada."""
    resolution = PiPointResolution(
        status=ResolutionStatus.RESOLVED,
        tag=TAG,
        items=({
            "WebId": WEB_ID,
            "Name": TAG,
            "Descriptor": "VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
            "PointType": "Float32",
            "EngineeringUnits": "mm/s",
        },),
        transport_used="batch",
    )
    mock_resolver = AsyncMock(return_value=resolution)
    collector = PiDataCollector(resolver=mock_resolver)
    result = await collector.fetch_one(TAG, "2026-08-02T16:17:38-03:00", "2026-08-03T16:17:38-03:00")

    from domain.analysis.models import AnalysisError
    assert not isinstance(result, AnalysisError), (
        f"esperado sucesso, mas recebeu: {result.code if isinstance(result, AnalysisError) else result}"
    )
    assert result.metadata.tag == TAG
    assert result.metadata.descriptor == "VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO"


@pytest.mark.asyncio
async def test_batch_primary_finds_tag():
    """Batch (transporte primário) deve encontrar a tag."""
    mock_batch = AsyncMock(return_value=_batch_response_resolved())
    mock_get = AsyncMock(return_value=_get_response_not_found())

    from domain.pims.clients.pi_point_resolver import resolve_pi_point
    result = await resolve_pi_point(TAG, batch_fn=mock_batch, get_fn=mock_get)

    assert result.status == ResolutionStatus.RESOLVED
    assert result.tag == TAG
    assert result.transport_used == "batch"
    assert result.items[0]["WebId"] == WEB_ID
    mock_get.assert_not_awaited()
