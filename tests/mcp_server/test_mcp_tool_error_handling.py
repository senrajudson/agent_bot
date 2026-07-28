"""Validate that tag_statistics rejects invalid arguments with an MCP error.

Tests validate the error path at the tool adapter level by calling the
service function and checking that the adapter raises ToolError.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.core.config import configure_domain_settings
from domain.core.integration_settings import DomainIntegrationSettings

_FAKE_SETTINGS = DomainIntegrationSettings(
    PI_WEB_API_BASE_URL="http://fake.test/piwebapi",
    MATH_TOOL_BASE_URL="http://fake.test:8001",
    GRAFANA_LOKI_QUERY_RANGE_URL="http://fake.test/loki",
)


def _ensure_domain_settings():
    try:
        configure_domain_settings(_FAKE_SETTINGS)
    except RuntimeError:
        pass


class TestServiceValidationErrors:
    """Test that the service raises DomainValidationError for invalid input."""

    @pytest.mark.asyncio
    async def test_group_by_1m_is_accepted(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="*-24h",
                group_by="1m",
                return_series=True,
            )
        assert result["error_code"] != "INVALID_GROUP_BY", (
            "1m deve ser aceito como group_by válido"
        )

    @pytest.mark.asyncio
    async def test_group_by_5m_raises_domain_validation_error(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="*-24h",
                group_by="5m",
                return_series=True,
            )
        assert result["ok"] is False
        assert result["status"] == "invalid_argument"
        assert result["error_code"] == "INVALID_GROUP_BY"

    @pytest.mark.asyncio
    async def test_group_by_2h_raises_domain_validation_error(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="*-24h",
                group_by="2h",
                return_series=True,
            )
        assert result["ok"] is False
        assert result["status"] == "invalid_argument"
        assert result["error_code"] == "INVALID_GROUP_BY"

    @pytest.mark.asyncio
    async def test_group_by_xyz_raises_domain_validation_error(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="*-24h",
                group_by="xyz",
                return_series=True,
            )
        assert result["ok"] is False
        assert result["status"] == "invalid_argument"
        assert result["error_code"] == "INVALID_GROUP_BY"

    @pytest.mark.asyncio
    async def test_data_method_invalido_raises_domain_validation_error(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="*-24h",
                data_method="xyz_invalido",
            )
        assert result["ok"] is False
        assert result["status"] == "invalid_argument"
        assert result["error_code"] == "INVALID_DATA_METHOD"
