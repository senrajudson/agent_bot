"""Tests for error code mapping from resolver to public contract (D6/A1).

Maps: INVALID_TIME_EXPRESSION, UNSUPPORTED_TIME_EXPRESSION, TIME_RESOLUTION_ERROR
→ INVALID_TIMESTAMP.
Preserves: INVALID_TIME_WINDOW.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch

from domain.shared.errors import DomainValidationError, ValidationErrorCode


def _make_domain_error(code: ValidationErrorCode, message: str = "test") -> DomainValidationError:
    return DomainValidationError(code=code, message=message)


class TestErrorMappingAnalyze:
    """Error mapping in analyze_pi_tag_behavior."""

    def test_invalid_time_expression_maps_to_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.INVALID_TIME_EXPRESSION),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="T", start_time="", end_time="*", zero_policy="suspicious"
                ))

    def test_unsupported_time_expression_maps_to_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="T", start_time="*-abc", end_time="*", zero_policy="suspicious"
                ))

    def test_time_resolution_error_maps_to_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.TIME_RESOLUTION_ERROR),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="T", start_time="*-xh", end_time="*", zero_policy="suspicious"
                ))

    def test_invalid_time_window_preserved(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.INVALID_TIME_WINDOW),
        ):
            with pytest.raises(ToolError, match="INVALID_TIME_WINDOW"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="T", start_time="*", end_time="*", zero_policy="suspicious"
                ))

    def test_error_message_sanitized(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(
                ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION,
                "Token ou formato temporal não suportado: '*-abc'.",
            ),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP") as exc_info:
                asyncio.run(analyze_pi_tag_behavior(
                    tag="T", start_time="*-abc", end_time="*", zero_policy="suspicious"
                ))
            error_str = str(exc_info.value)
            assert "traceback" not in error_str.lower()
            assert "File" not in error_str


class TestErrorMappingReport:
    """Error mapping in generate_pi_tags_analysis_report."""

    def test_invalid_time_expression_maps_to_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.INVALID_TIME_EXPRESSION),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T"], start_time="", end_time="*", zero_policy="invalid"
                ))

    def test_unsupported_time_expression_maps_to_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T"], start_time="*-abc", end_time="*", zero_policy="invalid"
                ))

    def test_time_resolution_error_maps_to_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.TIME_RESOLUTION_ERROR),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T"], start_time="*-xh", end_time="*", zero_policy="invalid"
                ))

    def test_invalid_time_window_preserved(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from fastmcp.exceptions import ToolError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=_make_domain_error(ValidationErrorCode.INVALID_TIME_WINDOW),
        ):
            with pytest.raises(ToolError, match="INVALID_TIME_WINDOW"):
                asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T"], start_time="*", end_time="*", zero_policy="invalid"
                ))
