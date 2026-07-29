import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest
from mcp_server.services.delivery.contracts import ArtifactManifest


_DOMAIN_CONFIGURED = False


def _ensure_domain_settings():
    global _DOMAIN_CONFIGURED
    if _DOMAIN_CONFIGURED:
        return
    from domain.core.config import configure_domain_settings, _reset_domain_settings
    from domain.core.integration_settings import DomainIntegrationSettings
    _reset_domain_settings(test_only=True)
    configure_domain_settings(DomainIntegrationSettings(
        PI_WEB_API_BASE_URL="http://fake",
        PI_SERVER_NAME="PIMS",
        MATH_TOOL_BASE_URL="http://fake",
        MATH_TOOL_TIMEOUT_SECONDS=10,
        GRAFANA_LOKI_QUERY_RANGE_URL="http://fake",
        GRAFANA_BEARER_TOKEN="fake",
        REDIS_URL="redis://fake",
    ))
    _DOMAIN_CONFIGURED = True


class TestExecutarEstatisticaServiceArtifact:
    """Valida que o service bifurca corretamente: flag off = legado, flag on = artifact."""

    @pytest.mark.asyncio
    async def test_flag_off_preserves_series(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service

        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [{"Timestamp": "2026-07-06T12:00:00-03:00", "Value": {"Value": 100.0}}]
            },
        }

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ), patch(
            "domain.analytics.services.math_tool_service.call_stats",
            AsyncMock(return_value={"ok": True, "result": {"sum": 100.0}}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                summary_type="Average",
                summary_duration="1d",
                calculation_basis="TimeWeighted",
                return_series=False,
                drive_artifact_delivery=False,
            )

        assert result["ok"] is True
        assert "delivery" not in result

    @pytest.mark.asyncio
    async def test_flag_on_artifact(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service

        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [{"Timestamp": "2026-07-06T12:00:00-03:00", "Value": {"Value": 100.0}}]
            },
        }

        async def fake_publisher(series_items, meta):
            return {
                "schema_version": "1.0",
                "status": "success",
                "delivery": "drive_artifact",
                "tool_name": "tag_statistics",
                "request_summary": {"tags_processed": 1},
                "artifact": {
                    "format": "csv",
                    "filename": "test.csv",
                    "mime_type": "text/csv",
                    "row_count": len(series_items),
                    "column_count": 5,
                    "size_bytes": 5000,
                    "view_url": "https://drive.google.com/view",
                },
                "warnings": [],
                "errors_summary": [],
            }

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                summary_type="Average",
                summary_duration="1d",
                calculation_basis="TimeWeighted",
                group_by="1h",
                return_series=True,
                drive_artifact_delivery=True,
                artifact_publisher=fake_publisher,
            )

        assert result["ok"] is True
        assert result["delivery"] == "drive_artifact"
        assert result["tool_result"]["status"] == "success"
        assert "series" not in str(result.get("tool_result", {}).get("results", []))
        assert "drive.google.com" in result["output"]
        assert "Visualizar" in result["output"]
        assert "Baixar" not in result["output"]

    @pytest.mark.asyncio
    async def test_scalar_unaffected(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service

        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [{"Timestamp": "2026-07-06T12:00:00-03:00", "Value": {"Value": 100.0}}]
            },
        }

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ), patch(
            "domain.analytics.services.math_tool_service.call_stats",
            AsyncMock(return_value={"ok": True, "result": {"mean": 100.0}}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                drive_artifact_delivery=True,
            )

        assert result["ok"] is True
        assert "delivery" not in result


class TestSummaryDefaults:
    """Valida defaults de Summary (T007, T008)."""

    @pytest.mark.asyncio
    async def test_summary_without_summary_type(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service
        pi_response = {"point_metadata": {}, "raw_data": {}}
        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["TAG_A"], operation="mean",
                start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z",
                data_method="summary",
            )
        assert result is not None

    @pytest.mark.asyncio
    async def test_summary_without_any(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service
        pi_response = {"point_metadata": {}, "raw_data": {}}
        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["TAG_A"], operation="sum",
                start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z",
                data_method="summary",
            )
        assert result is not None

    @pytest.mark.asyncio
    async def test_summary_with_explicit_values(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service
        pi_response = {"point_metadata": {}, "raw_data": {}}
        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["TAG_A"], operation="mean",
                start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z",
                data_method="summary",
                summary_type="Maximum", summary_duration="2h",
                calculation_basis="EventWeighted",
            )
        assert result is not None

    @pytest.mark.asyncio
    async def test_recorded_without_summary_params(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service
        pi_response = {"point_metadata": {}, "raw_data": {}}
        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["TAG_A"], operation="mean",
                start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z",
                data_method="recorded",
            )
        assert result is not None

    @pytest.mark.asyncio
    async def test_interpolated_without_summary_params(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service
        pi_response = {"point_metadata": {}, "raw_data": {}}
        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["TAG_A"], operation="mean",
                start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z",
                data_method="interpolated",
            )
        assert result is not None

    @pytest.mark.asyncio
    async def test_three_consecutive_calls(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service
        pi_response = {"point_metadata": {}, "raw_data": {}}
        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            for _ in range(3):
                result = await executar_estatistica_tags_service(
                    tags=["TAG_A"], operation="mean",
                    start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z",
                    data_method="summary",
                )
                assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_calls(self):
        _ensure_domain_settings()
        from domain.analytics.services.math_tool_service import executar_estatistica_tags_service
        pi_response = {"point_metadata": {}, "raw_data": {}}
        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            tasks = [
                executar_estatistica_tags_service(
                    tags=["TAG_A"], operation="mean" if i % 2 == 0 else "sum",
                    start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z",
                    data_method="summary",
                )
                for i in range(5)
            ]
            results = await asyncio.gather(*tasks)
            for r in results:
                assert r is not None
