from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, patch

import pytest


def _make_pi_response(items: list[dict]) -> dict:
    return {
        "raw_data": {"Items": items},
        "point_metadata": {"EngineeringUnits": "Nm3/h", "PointType": "Analog"},
    }


def _assert_success(result) -> None:
    if isinstance(result, dict):
        assert result.get("delivery") == "drive_artifact", (
            f"Unexpected dict result: {result}"
        )
        assert result.get("status") == "success"
    else:
        assert isinstance(result, str)


@pytest.fixture(autouse=True)
def _reload_mcp_server():
    """Reload server module so its module-level configure_domain_settings
    runs regardless of prior test state in the full suite."""
    import mcp_server.server
    importlib.reload(mcp_server.server)
    yield


class TestTagStatisticsFastMCP:
    """Tests tag_statistics via the FastMCP tool function with mocked PI client."""

    @pytest.mark.asyncio
    async def test_relative_time_success_first_call(self):
        from mcp_server.server import tag_statistics
        from datetime import datetime, timedelta, timezone

        anchor = datetime.now(timezone.utc)
        pi_items = []
        for i in range(60):
            ts = (anchor - timedelta(hours=1) + timedelta(minutes=i)).isoformat()
            pi_items.append({
                "Timestamp": ts,
                "Value": float(100 + i),
                "Good": True,
                "Questionable": False,
            })

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=_make_pi_response(pi_items)),
        ):
            result = await tag_statistics.fn(
                tags=["TAG_TESTE"],
                operation="mean",
                start_time="*-1h",
                end_time="*",
                data_method="interpolated",
                return_series=True,
                group_by="1h",
            )

        _assert_success(result)

    @pytest.mark.asyncio
    async def test_three_consecutive_calls(self):
        from mcp_server.server import tag_statistics
        from datetime import datetime, timedelta, timezone

        anchor = datetime.now(timezone.utc)
        pi_items = []
        for i in range(5):
            ts = (anchor - timedelta(hours=1) + timedelta(minutes=i * 12)).isoformat()
            pi_items.append({
                "Timestamp": ts,
                "Value": float(100 + i),
                "Good": True,
                "Questionable": False,
            })

        mock_return = _make_pi_response(pi_items)

        for _ in range(3):
            with patch(
                "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
                AsyncMock(return_value=mock_return),
            ):
                result = await tag_statistics.fn(
                    tags=["TAG_TESTE"],
                    operation="mean",
                    start_time="*-1h",
                    end_time="*",
                    data_method="interpolated",
                    return_series=True,
                    group_by="1h",
                )

            _assert_success(result)

    @pytest.mark.asyncio
    async def test_absolute_iso_still_works(self):
        from mcp_server.server import tag_statistics
        from datetime import datetime, timedelta, timezone

        anchor = datetime.now(timezone.utc)
        pi_items = []
        for i in range(5):
            ts = (anchor - timedelta(hours=1) + timedelta(minutes=i * 12)).isoformat()
            pi_items.append({
                "Timestamp": ts,
                "Value": float(100 + i),
                "Good": True,
                "Questionable": False,
            })

        start_iso = (anchor - timedelta(hours=1)).isoformat()
        end_iso = anchor.isoformat()

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=_make_pi_response(pi_items)),
        ):
            result = await tag_statistics.fn(
                tags=["TAG_TESTE"],
                operation="mean",
                start_time=start_iso,
                end_time=end_iso,
                data_method="interpolated",
                return_series=False,
            )

        _assert_success(result)
