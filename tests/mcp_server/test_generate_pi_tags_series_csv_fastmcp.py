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
        assert first_ts.endswith("-03:00"), f"Timestamp deve ter offset SP, got: {first_ts}"
        assert "T" in first_ts and len(first_ts) >= 25, f"Formato ISO incompleto: {first_ts}"

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


class TestExtractTimestampNormalization:
    """Testes unitários para _extract_timestamp — CA-01 a CA-12."""

    def _extract(self, ts_raw):
        from domain.pims.services.generate_pi_tags_series_csv_service import (
            _extract_timestamp,
        )
        return _extract_timestamp(ts_raw)

    def test_z_suffix_converts_to_sp(self):
        """CA-01: Z (UTC) → -03:00 (America/Sao_Paulo)."""
        assert self._extract("2026-08-03T12:48:26.616344Z") == "2026-08-03T09:48:26.616344-03:00"

    def test_utc_offset_converts_to_sp(self):
        """CA-02: +00:00 → -03:00."""
        assert self._extract("2026-08-03T12:48:26.616344+00:00") == "2026-08-03T09:48:26.616344-03:00"

    def test_already_in_sp_is_idempotent(self):
        """CA-03: -03:00 → -03:00 (idempotente)."""
        assert self._extract("2026-08-03T09:48:26.616344-03:00") == "2026-08-03T09:48:26.616344-03:00"

    def test_other_offset_converts_correctly(self):
        """CA-04: +04:00 → -03:00 (preservando instante absoluto)."""
        assert self._extract("2026-08-03T13:48:26.616344+04:00") == "2026-08-03T06:48:26.616344-03:00"

    def test_naive_treated_as_utc(self):
        """CA-05: naive (sem tzinfo) → tratado como UTC → -03:00."""
        assert self._extract("2026-08-03T12:48:26.616344") == "2026-08-03T09:48:26.616344-03:00"

    def test_date_change_during_conversion(self):
        """CA-06: 02:30Z em 04/08 → 23:30-03:00 em 03/08 (mudança de data)."""
        assert self._extract("2026-08-04T02:30:00Z") == "2026-08-03T23:30:00-03:00"

    def test_none_returns_none(self):
        """CA-07: None → None."""
        assert self._extract(None) is None

    def test_empty_string_returns_none(self):
        """CA-08: "" → None."""
        assert self._extract("") is None

    def test_invalid_string_returns_none(self):
        """CA-09: string inválida → None."""
        assert self._extract("invalid-string") is None

    def test_no_microseconds(self):
        """CA-10: sem microssegundos → preserva formato."""
        assert self._extract("2026-08-03T12:48:26Z") == "2026-08-03T09:48:26-03:00"

    def test_non_string_type_returns_none(self):
        """CA-11: tipo não-string (int) → None."""
        assert self._extract(1234567890) is None
