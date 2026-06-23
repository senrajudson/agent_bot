"""Tests for application Queries and Handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.queries.base import Query, QueryHandler
from app.application.queries.get_conversation_memory import (
    GetConversationMemory,
    GetConversationMemoryHandler,
    GetConversationMemoryResult,
)
from app.application.queries.get_knowledge_context import (
    GetKnowledgeContext,
    GetKnowledgeContextHandler,
    GetKnowledgeContextResult,
)
from app.application.queries.get_pi_historical_series import (
    GetPiHistoricalSeries,
    GetPiHistoricalSeriesHandler,
    GetPiHistoricalSeriesResult,
)
from app.application.queries.get_pi_tag_current_value import (
    GetPiTagCurrentValue,
    GetPiTagCurrentValueHandler,
    GetPiTagCurrentValueResult,
)
from app.application.queries.get_pims_status import (
    GetPimsStatus,
    GetPimsStatusHandler,
    GetPimsStatusResult,
)
from app.domain.enums import TemporalDataMethod
from app.domain.errors import TagNotFoundError
from app.domain.value_objects import CalculationBasis, PiWebId, SummaryType, TimeWindow


# =========================================================================
# Base abstractions
# =========================================================================
class TestQueryBase:
    def test_query_is_frozen_dataclass(self) -> None:
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class DummyQuery(Query):
            value: str

        q = DummyQuery(value="test")
        assert q.value == "test"


# =========================================================================
# GetConversationMemory
# =========================================================================
class TestGetConversationMemory:
    @pytest.mark.asyncio
    async def test_loads_turns_and_formats(self, mock_conversation_memory) -> None:
        handler = GetConversationMemoryHandler(mock_conversation_memory)
        result = await handler.handle(
            GetConversationMemory(conversation_id="conv-1")
        )
        mock_conversation_memory.load_turns.assert_awaited_once_with("conv-1", None)
        mock_conversation_memory.format_for_prompt.assert_called_once()
        assert len(result.turns) == 1
        assert result.context == "> user: qual o valor"

    @pytest.mark.asyncio
    async def test_passes_max_turns(self, mock_conversation_memory) -> None:
        handler = GetConversationMemoryHandler(mock_conversation_memory)
        await handler.handle(
            GetConversationMemory(conversation_id="c1", max_turns=4)
        )
        mock_conversation_memory.load_turns.assert_awaited_once_with("c1", 4)

    @pytest.mark.asyncio
    async def test_empty_conversation_id(self, mock_conversation_memory) -> None:
        mock_conversation_memory.load_turns = AsyncMock(return_value=[])
        mock_conversation_memory.format_for_prompt = MagicMock(return_value="")
        handler = GetConversationMemoryHandler(mock_conversation_memory)
        result = await handler.handle(
            GetConversationMemory(conversation_id="")
        )
        assert result.turns == []
        assert result.context == ""


# =========================================================================
# GetKnowledgeContext
# =========================================================================
class TestGetKnowledgeContext:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, mock_knowledge_repo) -> None:
        handler = GetKnowledgeContextHandler(mock_knowledge_repo)
        result = await handler.handle(
            GetKnowledgeContext(query="valor da tag X")
        )
        mock_knowledge_repo.build_context.assert_called_once_with(
            query="valor da tag X", top_k=3, include_fixed=True
        )
        assert result.context == "FAKE CONTEXT"

    @pytest.mark.asyncio
    async def test_custom_top_k(self, mock_knowledge_repo) -> None:
        handler = GetKnowledgeContextHandler(mock_knowledge_repo)
        await handler.handle(
            GetKnowledgeContext(query="X", top_k=5, include_fixed=False)
        )
        mock_knowledge_repo.build_context.assert_called_once_with(
            query="X", top_k=5, include_fixed=False
        )


# =========================================================================
# GetPiTagCurrentValue
# =========================================================================
class TestGetPiTagCurrentValue:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, mock_pi_repo) -> None:
        handler = GetPiTagCurrentValueHandler(mock_pi_repo)
        result = await handler.handle(
            GetPiTagCurrentValue(tag="LFI_RB3_VAZ_GN_TOTAL")
        )
        mock_pi_repo.get_point_by_tag.assert_awaited_once_with("LFI_RB3_VAZ_GN_TOTAL")
        mock_pi_repo.get_current_value.assert_awaited_once()
        assert result.point.name == "LFI_RB3_VAZ_GN_TOTAL"
        assert result.value.value == 1523.4

    @pytest.mark.asyncio
    async def test_tag_not_found(self, mock_pi_repo) -> None:
        mock_pi_repo.get_point_by_tag = AsyncMock(
            side_effect=Exception("404 Not Found")
        )
        handler = GetPiTagCurrentValueHandler(mock_pi_repo)
        with pytest.raises(TagNotFoundError, match="NONEXISTENT"):
            await handler.handle(GetPiTagCurrentValue(tag="NONEXISTENT"))


# =========================================================================
# GetPiHistoricalSeries
# =========================================================================
class TestGetPiHistoricalSeries:
    @pytest.mark.asyncio
    async def test_recorded_method(self, mock_pi_repo) -> None:
        handler = GetPiHistoricalSeriesHandler(mock_pi_repo)
        result = await handler.handle(
            GetPiHistoricalSeries(
                web_id=PiWebId("W1"),
                window=TimeWindow(start="2026-01-01", end="2026-01-31"),
                method=TemporalDataMethod.RECORDED,
                max_count=1000,
            )
        )
        mock_pi_repo.get_recorded_series.assert_awaited_once()
        assert result.series.points == [("2026-06-23", 1500.0)]

    @pytest.mark.asyncio
    async def test_interpolated_method(self, mock_pi_repo) -> None:
        handler = GetPiHistoricalSeriesHandler(mock_pi_repo)
        result = await handler.handle(
            GetPiHistoricalSeries(
                web_id=PiWebId("W1"),
                window=TimeWindow(start="2026-01-01", end="2026-01-31"),
                method=TemporalDataMethod.INTERPOLATED,
                interval="5m",
            )
        )
        mock_pi_repo.get_interpolated_series.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_summary_method(self, mock_pi_repo) -> None:
        handler = GetPiHistoricalSeriesHandler(mock_pi_repo)
        result = await handler.handle(
            GetPiHistoricalSeries(
                web_id=PiWebId("W1"),
                window=TimeWindow(start="2026-01-01", end="2026-01-31"),
                method=TemporalDataMethod.SUMMARY,
                summary_type=SummaryType.from_string("Average"),
                summary_duration="1h",
                calculation_basis=CalculationBasis.from_string("TimeWeighted"),
            )
        )
        mock_pi_repo.get_summary_series.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_method_raises(self, mock_pi_repo) -> None:
        handler = GetPiHistoricalSeriesHandler(mock_pi_repo)
        with pytest.raises(ValueError, match="Unknown method"):
            await handler.handle(
                GetPiHistoricalSeries(
                    web_id=PiWebId("W1"),
                    window=TimeWindow(start="2026-01-01", end="2026-01-31"),
                    method="invalid_method",  # type: ignore[arg-type]
                )
            )


# =========================================================================
# GetPimsStatus
# =========================================================================
class TestGetPimsStatus:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, mock_pims_ops_repo) -> None:
        handler = GetPimsStatusHandler(mock_pims_ops_repo)
        result = await handler.handle(GetPimsStatus(lookback_minutes=60))
        mock_pims_ops_repo.get_status_report.assert_awaited_once_with(60)
        assert result.report["total_logs"] == 100

    @pytest.mark.asyncio
    async def test_default_lookback(self, mock_pims_ops_repo) -> None:
        handler = GetPimsStatusHandler(mock_pims_ops_repo)
        result = await handler.handle(GetPimsStatus())
        mock_pims_ops_repo.get_status_report.assert_awaited_once_with(None)
