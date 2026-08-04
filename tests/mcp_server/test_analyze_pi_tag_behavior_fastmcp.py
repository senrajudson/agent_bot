from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from domain.analysis.models import AnalysisPoint, TagMetadata
from domain.analysis.services.pi_data_collector import CollectedData


MOCK_METADATA = TagMetadata(tag="LFI_TEST", point_type="numeric", descriptor="Test", engineering_units="Nm3/h")


class TestAnalyzePiTagBehavior:
    def test_valid_call_numeric(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        mock_data = CollectedData(
            metadata=MOCK_METADATA,
            recorded=[
                AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0),
                AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=20.0),
            ],
            interpolated=[
                AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0),
                AnalysisPoint(timestamp="2026-01-01T00:05:00-03:00", value=15.0),
            ],
        )

        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=mock_data)
            import asyncio
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="LFI_TEST",
                start_time="2026-01-01T00:00:00-03:00",
                end_time="2026-01-01T01:00:00-03:00",
            ))

        assert isinstance(result, str)
        assert "## Resumo" in result
        assert "LFI_TEST" in result

    def test_tag_not_found(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from domain.analysis.models import AnalysisError

        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(
                return_value=AnalysisError(tag="X", code="TAG_NOT_FOUND", message="not found", retryable=False)
            )
            import asyncio
            with pytest.raises(Exception, match="TAG_NOT_FOUND"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="X",
                    start_time="2026-01-01T00:00:00-03:00",
                    end_time="2026-01-01T01:00:00-03:00",
                ))

    def test_invalid_digital_set(self) -> None:
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from domain.analysis.models import AnalysisError

        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(
                return_value=AnalysisError(tag="ACI_VALVE", code="INVALID_DIGITAL_SET", message="invalid ds", retryable=False)
            )
            import asyncio
            with pytest.raises(Exception, match="INVALID_DIGITAL_SET"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="ACI_VALVE",
                    start_time="2026-01-01T00:00:00-03:00",
                    end_time="2026-01-01T01:00:00-03:00",
                ))
