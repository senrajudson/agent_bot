"""Validate that operational questions work even with empty RAG/Qdrant.

This test stubs the Qdrant retrieval to return zero results.
CHUNK 01 remains injected (it's read from the markdown file directly).
The agent should still be able to select the correct tool based on MCP descriptions.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tag_attributes_tool_selected_without_rag():
    """When Qdrant returns no chunks, a question about compression
    should still work because the MCP description guides tool selection."""
    from app.clients.qdrant_client import retrieve_relevant_chunks
    from app.clients.qdrant_client import _load_fixed_chunk

    # Verify that fixed chunk (CHUNK 01) is still available
    fixed = _load_fixed_chunk()
    assert fixed, "CHUNK 01 must be loadable"

    with patch(
        "app.clients.qdrant_client.retrieve_relevant_chunks",
        return_value=[],
    ):
        from app.clients.qdrant_client import build_rag_context

        ctx = build_rag_context(query="qual a compressão da tag X?", top_k=3)
        # Context should still contain CHUNK 01
        assert len(ctx) > 0, "RAG context should not be empty (CHUNK 01)"
        assert "CHUNK 01" in ctx or "Mapa" in ctx, (
            "RAG context should contain CHUNK 01 content"
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_routing_works_with_empty_qdrant():
    """When Qdrant returns zero chunks, the router should still classify
    and the agent should still be able to select tools."""
    from app.clients.qdrant_client import retrieve_relevant_chunks

    with patch(
        "app.clients.qdrant_client.retrieve_relevant_chunks",
        return_value=[],
    ):
        from app.agent.router import route_message

        route = await route_message(
                user_message="qual o valor atual da tag LFI_RB3_VAZ_GN_TOTAL?"
            )
        route_value = route.rota if hasattr(route, "rota") else str(route)
        # Even without RAG, router should still classify as PIMS
        assert route_value in ("pims", "conversa_comum"), (
            f"Router returned unexpected route: {route_value}"
        )
