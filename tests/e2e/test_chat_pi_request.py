"""
End-to-end test for pi_request via POST /chat.

Tests the exact screenshot query: "encontre tags para mim na pi web api
relacionadas com a descrição 'bomba d'agua'"

Gated with pytest.mark.e2e; skipped if FastAPI app can't be imported
or if the running instance is unreachable.
"""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

RUNNING_URL = "http://localhost:8012"


def _app_reachable() -> bool:
    try:
        resp = httpx.get(f"{RUNNING_URL}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _app_reachable(),
    reason=f"Agent not reachable at {RUNNING_URL}",
)


@pytest.mark.asyncio
async def test_search_by_descriptor_returns_candidates():
    payload = {
        "message": "encontre tags para mim na pi web api relacionadas com a descrição 'bomba d'agua'",
        "conversation_id": "e2e-test-search-001",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{RUNNING_URL}/chat", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["categoria"] == "pims"
    assert data["tool_name"] in {"pi_request", "pi_agent"}
    assert data["output"] is not None
    assert len(data["output"]) > 10


@pytest.mark.asyncio
async def test_search_by_name_filter():
    payload = {
        "message": "busque tags com o nome parecido a VAZ_GN na pi web api",
        "conversation_id": "e2e-test-search-002",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{RUNNING_URL}/chat", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["categoria"] == "pims"


@pytest.mark.asyncio
async def test_tag_statistics_still_works():
    payload = {
        "message": "qual a média da tag LFI_RB3_VAZ_GN_TOTAL nas últimas 24 horas?",
        "conversation_id": "e2e-test-stats-001",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{RUNNING_URL}/chat", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["categoria"] == "pims"


@pytest.mark.asyncio
async def test_status_pims_still_works():
    payload = {
        "message": "o PIMS está funcionando normalmente?",
        "conversation_id": "e2e-test-status-001",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{RUNNING_URL}/chat", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_simple_value_query_no_context_variable_error():
    """Regression test: 'valor cdt158' must not trigger
    'Context variable not found: WebId' from ADK state injection."""
    payload = {
        "message": "valor cdt158",
        "conversation_id": "e2e-test-value-001",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{RUNNING_URL}/chat", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "Context variable not found" not in (data.get("output") or "")
    assert "Context variable not found" not in (data.get("answer_generation_error") or "")
    assert data["categoria"] == "pims"
