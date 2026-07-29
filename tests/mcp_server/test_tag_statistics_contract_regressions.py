"""Regressões contratuais de tag_statistics — validação das correções."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestTagStatisticsSeriesValidations:
    """Valida que tag_statistics rejeita combinações inválidas em modo série."""

    @pytest.fixture(autouse=True)
    def _setup_settings(self):
        from domain.core.config import _reset_domain_settings, configure_domain_settings
        from domain.core.integration_settings import DomainIntegrationSettings
        try:
            _reset_domain_settings(test_only=True)
        except RuntimeError:
            pass
        configure_domain_settings(DomainIntegrationSettings(
            PI_WEB_API_BASE_URL="http://pi.test/piwebapi",
            PI_SERVER_NAME="PIMS",
            MATH_TOOL_BASE_URL="http://math.test:8001",
        ))

    async def _run_service(self, **kwargs):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )
        return await executar_estatistica_tags_service(**kwargs)

    async def test_data_method_interpolated_with_series_rejected(self) -> None:
        result = await self._run_service(
            tags=["TAG_A"],
            operation="mean",
            start_time="2026-07-01T00:00:00-03:00",
            end_time="2026-07-01T01:00:00-03:00",
            data_method="interpolated",
            return_series=True,
            group_by="1m",
        )
        assert result.get("status") == "invalid_argument"
        assert "INVALID_DATA_METHOD_FOR_AGGREGATED_SERIES" in str(result.get("error_code", ""))

    async def test_data_method_recorded_with_series_rejected(self) -> None:
        result = await self._run_service(
            tags=["TAG_A"],
            operation="mean",
            start_time="2026-07-01T00:00:00-03:00",
            end_time="2026-07-01T01:00:00-03:00",
            data_method="recorded",
            return_series=True,
            group_by="1m",
        )
        assert result.get("status") == "invalid_argument"
        assert "INVALID_DATA_METHOD_FOR_AGGREGATED_SERIES" in str(result.get("error_code", ""))

    async def test_data_method_summary_with_series_accepted(self) -> None:
        result = await self._run_service(
            tags=["TAG_A"],
            operation="mean",
            start_time="2026-07-01T00:00:00-03:00",
            end_time="2026-07-01T01:00:00-03:00",
            data_method="summary",
            return_series=True,
            group_by="1m",
            summary_duration="1m",
            summary_type="Average",
            calculation_basis="TimeWeighted",
        )
        # A validação contratual passa. Pode retornar network_error ou no_data
        # porque o PI client não está mockado, mas não deve ser invalid_argument.
        assert result.get("status") not in ("invalid_argument",)

    async def test_scalar_with_interpolated_still_works(self) -> None:
        result = await self._run_service(
            tags=["TAG_A"],
            operation="mean",
            start_time="2026-07-01T00:00:00-03:00",
            end_time="2026-07-01T01:00:00-03:00",
            data_method="interpolated",
            interval="1m",
            return_series=False,
        )
        assert result.get("status") not in ("invalid_argument", "internal_error")

    async def test_scalar_with_recorded_still_works(self) -> None:
        result = await self._run_service(
            tags=["TAG_A"],
            operation="mean",
            start_time="2026-07-01T00:00:00-03:00",
            end_time="2026-07-01T01:00:00-03:00",
            data_method="recorded",
            return_series=False,
        )
        assert result.get("status") not in ("invalid_argument", "internal_error")

    async def test_scalar_with_summary_still_works(self) -> None:
        result = await self._run_service(
            tags=["TAG_A"],
            operation="mean",
            start_time="2026-07-01T00:00:00-03:00",
            end_time="2026-07-01T01:00:00-03:00",
            data_method="summary",
            return_series=False,
        )
        assert result.get("status") not in ("invalid_argument", "internal_error")
