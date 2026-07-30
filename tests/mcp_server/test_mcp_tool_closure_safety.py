"""
Testes de segurança de closures para MCP tools.

Valida que nenhuma tool MCP levanta UnboundLocalError quando parâmetros
opcionais são omitidos pelo LLM.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest

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
        REDIS_URL="redis://fake",
    ))
    _DOMAIN_CONFIGURED = True


class TestClosureSafety:
    """Valida que tools não crasham com UnboundLocalError quando parâmetros opcionais são omitidos."""

    @pytest.mark.asyncio
    async def test_tag_statistics_without_optional(self):
        _ensure_domain_settings()
        from mcp_server.server import tag_statistics

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={"point_metadata": {}, "raw_data": {"Items": []}}),
        ):
            result = await tag_statistics.run(arguments={  # type: ignore[attr-defined]
                "tags": ["TAG_A"], "operation": "mean",
                "start_time": "2026-01-01T00:00:00Z",
            })
        assert result is not None

    @pytest.mark.asyncio
    async def test_tag_calculus_without_optional(self):
        _ensure_domain_settings()
        from mcp_server.server import tag_calculus

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={"point_metadata": {}, "raw_data": {"Items": []}}),
        ), patch(
            "domain.analytics.services.math_tool_service.call_calculus",
            AsyncMock(return_value={"ok": True, "result": {"integral": 100.0}}),
        ):
            result = await tag_calculus.run(arguments={  # type: ignore[attr-defined]
                "tags": ["TAG_A"], "operation": "integral",
                "start_time": "2026-01-01T00:00:00Z",
            })
        assert result is not None

    @pytest.mark.asyncio
    async def test_consultar_tag_without_optional(self):
        _ensure_domain_settings()
        from mcp_server.server import consultar_tag

        with patch(
            "domain.pims.clients.pi_web_api_client.get_tags_data",
            AsyncMock(return_value={}),
        ), patch(
            "domain.pims.utils.digital_states.get_digital_set_states",
            AsyncMock(return_value=[]),
        ):
            result = await consultar_tag.run(arguments={  # type: ignore[attr-defined]
                "tags": ["TAG_A"],
            })
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_pi_points_without_optional(self):
        _ensure_domain_settings()
        from mcp_server.server import search_pi_points

        with patch(
            "domain.pims.clients.pi_web_api_client.get_point_by_tag",
            AsyncMock(return_value={}),
        ):
            result = await search_pi_points.run(arguments={  # type: ignore[attr-defined]
                "query": "test",
            })
        assert result is not None

    @pytest.mark.asyncio
    async def test_tag_attributes_tool_without_optional(self):
        _ensure_domain_settings()
        from mcp_server.server import tag_attributes_tool

        with patch(
            "domain.pims.clients.pi_web_api_client.get_point_by_tag",
            AsyncMock(return_value={}),
        ), patch(
            "domain.pims.services.tag_attributes_service.get_tag_attributes",
            AsyncMock(return_value={"ok": True, "output": "attributes"}),
        ):
            result = await tag_attributes_tool.run(arguments={  # type: ignore[attr-defined]
                "tag": "TAG_A",
            })
        assert result is not None

    @pytest.mark.asyncio
    async def test_status_pims_tool_without_optional(self):
        _ensure_domain_settings()
        from mcp_server.server import status_pims_tool

        with patch(
            "domain.pims_ops.services.status_pims_service.consultar_health_pi_web_api_service",
            AsyncMock(return_value='{"available":true,"latency_ms":0,"endpoint":"/dataservers","error":null}'),
        ):
            result = await status_pims_tool.run(arguments={})  # type: ignore[attr-defined]
        assert result is not None
