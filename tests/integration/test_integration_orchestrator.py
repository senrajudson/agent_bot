"""Integration tests — requires Docker services running.

Run with: pytest -m integration
"""
from __future__ import annotations

import os

import pytest


# Skip all integration tests if INTEGRATION_TEST env var is not set
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestOrchestratorIntegration:
    """Requires agent_bot running at localhost:8002."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self) -> None:
        """Health check against /health endpoint."""
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not installed")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:8002/health",
                timeout=5.0,
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_endpoint_pims_route(self) -> None:
        """Smoke test: PIMS route query against /chat."""
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not installed")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "http://localhost:8002/chat",
                json={
                    "message": "qual o valor da LFI_RB3_VAZ_GN_TOTAL",
                    "user_id": "integration-test",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["categoria"] == "pims"
