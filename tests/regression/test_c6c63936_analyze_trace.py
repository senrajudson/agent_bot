"""Regression test for trace c6c63936e6fbfde1 (T100-T107).

Reproduces the exact incident where analyze_pi_tag_behavior was called with
*-24h/* and returned INVALID_TIMESTAMP. After the fix, the tool should
normalize the period and deliver analysis.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch, AsyncMock

from domain.analysis.models import AnalysisPoint, TagMetadata
from domain.analysis.services.pi_data_collector import CollectedData
from domain.shared.time.pi_time_resolver import ResolvedTimeRange


TRACE_ID = "c6c63936e6fbfde1"
TAG = "LFS_RB2_AC_MA_VIB_VEL"

METADATA = TagMetadata(
    tag=TAG,
    point_type="numeric",
    descriptor="VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
    engineering_units="mm/s",
)


def _make_data() -> CollectedData:
    return CollectedData(
        metadata=METADATA,
        recorded=[
            AnalysisPoint(timestamp="2026-08-03T08:56:00-03:00", value=1.2),
            AnalysisPoint(timestamp="2026-08-03T09:01:00-03:00", value=1.5),
            AnalysisPoint(timestamp="2026-08-03T09:06:00-03:00", value=1.3),
        ],
        interpolated=[
            AnalysisPoint(timestamp="2026-08-03T08:56:00-03:00", value=1.2),
            AnalysisPoint(timestamp="2026-08-03T09:01:00-03:00", value=1.4),
            AnalysisPoint(timestamp="2026-08-03T09:06:00-03:00", value=1.3),
        ],
    )


class TestTraceC6c63936Regression:
    """Trace c6c63936e6fbfde1 regression test."""

    def test_star_24h_delivers_analysis(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        resolved = ResolvedTimeRange(
            start=__import__("datetime").datetime(2026, 8, 3, 8, 56, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")),
            end=__import__("datetime").datetime(2026, 8, 4, 8, 56, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")),
            start_iso="2026-08-03T08:56:00-03:00",
            end_iso="2026-08-04T08:56:00-03:00",
            timezone="America/Sao_Paulo",
            input_kind="relative",
        )

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=resolved,
        ) as mock_resolve, patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag=TAG,
                start_time="*-24h",
                end_time="*",
                zero_policy="suspicious",
            ))

            # T104: single call to resolver
            assert mock_resolve.call_count == 1

            # T105: useful response delivered
            assert isinstance(result, str)
            assert TAG in result

            # T106: no INVALID_TIMESTAMP for valid token
            assert "INVALID_TIMESTAMP" not in result

    def test_iso_valid_still_works(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        resolved = ResolvedTimeRange(
            start=__import__("datetime").datetime(2026, 8, 3, 10, 0, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")),
            end=__import__("datetime").datetime(2026, 8, 4, 10, 0, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")),
            start_iso="2026-08-03T10:00:00-03:00",
            end_iso="2026-08-04T10:00:00-03:00",
            timezone="America/Sao_Paulo",
            input_kind="absolute",
        )

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=resolved,
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag=TAG,
                start_time="2026-08-03T10:00:00-03:00",
                end_time="2026-08-04T10:00:00-03:00",
                zero_policy="suspicious",
            ))
            assert isinstance(result, str)
            assert TAG in result
