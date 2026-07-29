from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from domain.core.config import _reset_domain_settings, configure_domain_settings
from domain.core.integration_settings import DomainIntegrationSettings


_FAKE_SETTINGS = DomainIntegrationSettings(
    PI_WEB_API_BASE_URL="http://fake.test/piwebapi",
    MATH_TOOL_BASE_URL="http://fake.test:8001",
    GRAFANA_LOKI_QUERY_RANGE_URL="http://fake.test/loki",
)


TZ = ZoneInfo("America/Sao_Paulo")
ANCHOR = datetime(2026, 7, 29, 11, 0, 0, tzinfo=TZ)


def _make_pi_response(items: list[dict], metadata: dict | None = None) -> dict:
    return {
        "raw_data": {
            "Items": items,
            "Name": "TAG_TESTE",
        },
        "point_metadata": metadata or {
            "EngineeringUnits": "Nm3/h",
            "PointType": "Analog",
        },
    }


class TestGroupPointsByPeriod:
    """Direct unit tests for _group_points_by_period with non-empty synthetic points."""

    @pytest.fixture(autouse=True)
    def _setup_settings(self):
        _reset_domain_settings(test_only=True)
        configure_domain_settings(_FAKE_SETTINGS)

    def _make_points(self, count: int, start_dt: datetime, interval_minutes: int = 1) -> list[dict]:
        points = []
        for i in range(count):
            ts = start_dt + timedelta(minutes=i * interval_minutes)
            points.append({"timestamp": ts.isoformat(), "value": float(i + 1)})
        return points

    def test_single_bucket_hourly(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period

        start = ANCHOR - timedelta(hours=1)
        end = ANCHOR
        points = self._make_points(5, start, interval_minutes=12)

        buckets = _group_points_by_period(points, start=start, end=end, group_by="1h")

        assert len(buckets) == 1
        assert buckets[0]["period_start"] == start.isoformat()
        assert buckets[0]["period_end"] == end.isoformat()
        assert len(buckets[0]["points"]) == 5
        assert buckets[0]["duration_seconds"] == 3600

    def test_single_bucket_boundary_excludes_end(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period

        start = ANCHOR - timedelta(hours=1)
        end = ANCHOR
        points = self._make_points(5, start, interval_minutes=12)
        points.append({"timestamp": end.isoformat(), "value": 999})

        buckets = _group_points_by_period(points, start=start, end=end, group_by="1h")

        assert len(buckets[0]["points"]) == 5
        for p in buckets[0]["points"]:
            assert p["value"] != 999

    def test_multiple_buckets_1m(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period

        start = ANCHOR - timedelta(hours=1)
        end = ANCHOR
        points = self._make_points(60, start, interval_minutes=1)

        buckets = _group_points_by_period(points, start=start, end=end, group_by="1m")

        assert len(buckets) == 60
        for i, b in enumerate(buckets):
            assert len(b["points"]) == 1

    def test_empty_points_no_error(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period

        start = ANCHOR - timedelta(hours=1)
        end = ANCHOR
        buckets = _group_points_by_period([], start=start, end=end, group_by="1h")

        assert len(buckets) == 1
        assert len(buckets[0]["points"]) == 0


class TestServiceRelativeTime:
    """Integration test for the service with resolved absolute times."""

    @pytest.fixture(autouse=True)
    def _setup_settings(self):
        _reset_domain_settings(test_only=True)
        configure_domain_settings(_FAKE_SETTINGS)

    @pytest.mark.asyncio
    async def test_service_with_resolved_absolutes(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        start_iso = (ANCHOR - timedelta(hours=1)).isoformat()
        end_iso = ANCHOR.isoformat()

        pi_items = []
        for i in range(60):
            ts = (ANCHOR - timedelta(hours=1) + timedelta(minutes=i)).isoformat()
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
            result = await executar_estatistica_tags_service(
                tags=["TAG_TESTE"],
                operation="mean",
                start_time=start_iso,
                end_time=end_iso,
                group_by="1m",
                return_series=True,
                data_method="interpolated",
                interval="1m",
            )

        assert result["ok"] is True
        assert len(result["tool_result"]["results"]) == 1
        series = result["tool_result"]["results"][0]["series"]
        assert len(series) == 60

    @pytest.mark.asyncio
    async def test_service_scalar_preserved(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        start_iso = (ANCHOR - timedelta(hours=1)).isoformat()
        end_iso = ANCHOR.isoformat()

        pi_items = []
        for i in range(10):
            ts = (ANCHOR - timedelta(hours=1) + timedelta(minutes=i * 6)).isoformat()
            pi_items.append({
                "Timestamp": ts,
                "Value": float(100 + i),
                "Good": True,
                "Questionable": False,
            })

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=_make_pi_response(pi_items)),
        ), patch(
            "domain.analytics.services.math_tool_service.call_stats",
            AsyncMock(return_value={"ok": True, "result": {"mean": 105.0}}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["TAG_TESTE"],
                operation="mean",
                start_time=start_iso,
                end_time=end_iso,
            )

        assert result["ok"] is True
