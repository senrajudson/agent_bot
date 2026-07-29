from __future__ import annotations

import pytest

from domain.shared.errors import DomainValidationError, ValidationErrorCode


class TestTimeResolutionErrors:
    """Tests that invalid time expressions produce DomainValidationError with
    the correct error code."""

    def _call_service_with(self, start_time: str, end_time: str = "*"):
        from domain.shared.time import resolve_pi_time_range
        from datetime import datetime
        from zoneinfo import ZoneInfo

        anchor = datetime(2026, 7, 29, 11, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        return resolve_pi_time_range(start_time, end_time, now=anchor)

    def test_empty_start_expression(self):
        with pytest.raises(DomainValidationError) as exc:
            self._call_service_with("")
        assert exc.value.code == ValidationErrorCode.INVALID_TIME_EXPRESSION

    def test_invalid_pattern_xh(self):
        with pytest.raises(DomainValidationError) as exc:
            self._call_service_with("*-xh")
        assert exc.value.code == ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION

    def test_invalid_pattern_banana(self):
        with pytest.raises(DomainValidationError) as exc:
            self._call_service_with("*-1banana")
        assert exc.value.code == ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION

    def test_start_equal_end(self):
        with pytest.raises(DomainValidationError) as exc:
            self._call_service_with("*", "*")
        assert exc.value.code == ValidationErrorCode.INVALID_TIME_WINDOW

    def test_start_after_end(self):
        with pytest.raises(DomainValidationError) as exc:
            self._call_service_with(
                "2026-07-30T00:00:00-03:00", "2026-07-29T00:00:00-03:00"
            )
        assert exc.value.code == ValidationErrorCode.INVALID_TIME_WINDOW

    def test_iso_without_offset(self):
        with pytest.raises(DomainValidationError) as exc:
            self._call_service_with(
                "2026-07-29T10:00:00", "2026-07-29T11:00:00-03:00"
            )
        assert exc.value.code == ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION

    def test_unsupported_token_plus(self):
        with pytest.raises(DomainValidationError) as exc:
            self._call_service_with("*+1h")
        assert exc.value.code == ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION


class TestToolErrorPropagation:
    """Verifies that DomainValidationError from time resolution is caught
    by _mcp_safe_tool and transformed into ToolError."""

    @pytest.mark.asyncio
    async def test_tool_error_on_empty_start(self):
        from mcp_server.server import tag_statistics
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as exc:
            await tag_statistics.fn(
                tags=["TAG_TESTE"],
                operation="mean",
                start_time="",
                end_time="*",
            )
        assert "INVALID_TIME_EXPRESSION" in str(exc.value)

    @pytest.mark.asyncio
    async def test_tool_error_on_invalid_pattern(self):
        from mcp_server.server import tag_statistics
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as exc:
            await tag_statistics.fn(
                tags=["TAG_TESTE"],
                operation="mean",
                start_time="*-xh",
                end_time="*",
            )
        assert "UNSUPPORTED_TIME_EXPRESSION" in str(exc.value)

    @pytest.mark.asyncio
    async def test_tool_error_on_start_after_end(self):
        from mcp_server.server import tag_statistics
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as exc:
            await tag_statistics.fn(
                tags=["TAG_TESTE"],
                operation="mean",
                start_time="2026-07-30T00:00:00-03:00",
                end_time="2026-07-29T00:00:00-03:00",
            )
        assert "INVALID_TIME_WINDOW" in str(exc.value)
