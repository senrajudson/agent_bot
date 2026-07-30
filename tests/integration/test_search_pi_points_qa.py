"""Integration tests for search_pi_points — requires PI Web API running.

Run with: pytest -m integration

Validates that the strict AND path finds LFS_RB2_VELOPROC
for query "velocidade rb2" and rejects irrelevant tags.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

from domain.pims.services.search_points_service import (
    search_pi_points,
    _build_strict_result,
)


@pytest.mark.asyncio
class TestSearchPiPointsQA:
    """Requires PI Web API at PI_WEB_API_BASE_URL (defaults to PIMS)."""

    @pytest.mark.asyncio
    async def test_velocidade_rb2_encontra_veloproc(self) -> None:
        """Teste real no PI: velocidade rb2 → LFS_RB2_VELOPROC."""
        from mcp_server.core.config import settings

        if not settings.ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND:
            pytest.skip("Strict AND desabilitado. Defina ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND=true")

        result = await search_pi_points(
            query="velocidade rb2",
            search_mode="auto",
        )
        names = {item["name"] for item in result.get("items", [])}
        assert "LFS_RB2_VELOPROC" in names, (
            f"LFS_RB2_VELOPROC não encontrada. Items: {names}"
        )
        descs = " ".join(
            (item.get("description") or "") for item in result.get("items", [])
        )
        assert "CORRENTE" not in descs.upper(), (
            "Tag de corrente não deveria estar presente"
        )
        assert "RB3" not in descs.upper(), (
            "Tag de RB3 não deveria estar presente"
        )
        assert result.get("count", 0) <= 5
