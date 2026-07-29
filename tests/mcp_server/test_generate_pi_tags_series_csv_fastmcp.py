"""Testes FastMCP para a nova tool generate_pi_tags_series_csv."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


def _make_pi_response(rows: list[dict]) -> dict:
    return {
        "Items": rows,
        "EngineeringUnits": "m/min",
        "PointType": "Analog",
    }


def _make_interpolated_row(ts: str, value: float | None, good: bool = True) -> dict:
    row: dict = {
        "Timestamp": ts,
        "Value": value,
        "Good": good,
        "Questionable": False,
        "Substituted": False,
        "Annotated": False,
    }
    if value is None and not good:
        row["Errors"] = "No value"
    return row


class TestGeneratePiTagsSeriesCsvService:
    """Tests the service directly (core logic, no MCP decorator)."""

    @pytest.mark.asyncio
    async def test_no_data(self):
        from domain.pims.services.generate_pi_tags_series_csv_service import (
            generate_pi_tags_series_csv_service,
        )

        mock_response = {"Items": []}

        with patch(
            "domain.pims.services.generate_pi_tags_series_csv_service.get_interpolated_values_by_tag",
            AsyncMock(return_value=mock_response),
        ):
            result = await generate_pi_tags_series_csv_service(
                tags=["TAG_A"],
                start_time="*-1h",
                end_time="*",
                data_method="interpolated",
                interval="1m",
            )

        assert result.get("status") == "no_data"
        assert "rows" not in result or not result["rows"]

    @pytest.mark.asyncio
    async def test_interpolated_60_rows(self):
        from domain.pims.services.generate_pi_tags_series_csv_service import (
            generate_pi_tags_series_csv_service,
        )

        anchor = datetime.now(timezone.utc)
        items = []
        for i in range(60):
            ts = (anchor - timedelta(hours=1) + timedelta(minutes=i)).isoformat()
            items.append(_make_interpolated_row(ts, float(100 + i)))

        mock_response = _make_pi_response(items)

        with patch(
            "domain.pims.services.generate_pi_tags_series_csv_service.get_interpolated_values_by_tag",
            AsyncMock(return_value=mock_response),
        ):
            result = await generate_pi_tags_series_csv_service(
                tags=["TAG_A"],
                start_time="*-1h",
                end_time="*",
                data_method="interpolated",
                interval="1m",
            )

        assert result.get("status") == "success"
        rows = result.get("rows", [])
        assert len(rows) == 60
        first_ts = rows[0]["timestamp"]
        assert rows[0]["value"] == 100.0
        assert rows[0]["tag"] == "TAG_A"

    @pytest.mark.asyncio
    async def test_contract_error_invalid_tags(self):
        from domain.pims.services.generate_pi_tags_series_csv_service import (
            generate_pi_tags_series_csv_service,
        )

        from domain.shared.errors import DomainValidationError

        with pytest.raises(DomainValidationError):
            await generate_pi_tags_series_csv_service(
                tags=[f"TAG_{i}" for i in range(12)],
                start_time="*-1h",
                end_time="*",
                data_method="interpolated",
            )
