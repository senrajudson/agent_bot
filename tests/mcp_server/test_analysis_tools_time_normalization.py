"""Tests for temporal normalization in analysis tools (T040-T061).

Validates that analyze_pi_tag_behavior and generate_pi_tags_analysis_report
accept PI time tokens via resolve_pi_time_range before AnalysisRequest.
"""
from __future__ import annotations

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from domain.analysis.models import AnalysisPoint, TagMetadata
from domain.analysis.services.pi_data_collector import CollectedData
from domain.shared.time.pi_time_resolver import ResolvedTimeRange


ANCHOR = datetime(2026, 8, 4, 8, 56, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

MOCK_METADATA = TagMetadata(
    tag="LFS_RB2_AC_MA_VIB_VEL",
    point_type="numeric",
    descriptor="VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
    engineering_units="mm/s",
)


def _make_resolved(start_iso: str, end_iso: str) -> ResolvedTimeRange:
    return ResolvedTimeRange(
        start=datetime.fromisoformat(start_iso),
        end=datetime.fromisoformat(end_iso),
        start_iso=start_iso,
        end_iso=end_iso,
        timezone="America/Sao_Paulo",
        input_kind="relative",
    )


def _make_collected_data() -> CollectedData:
    return CollectedData(
        metadata=MOCK_METADATA,
        recorded=[
            AnalysisPoint(timestamp="2026-08-03T08:56:00-03:00", value=1.2),
            AnalysisPoint(timestamp="2026-08-03T09:01:00-03:00", value=1.5),
        ],
        interpolated=[
            AnalysisPoint(timestamp="2026-08-03T08:56:00-03:00", value=1.2),
            AnalysisPoint(timestamp="2026-08-03T09:01:00-03:00", value=1.4),
        ],
    )


def _resolved_24h():
    return _make_resolved("2026-08-03T08:56:00-03:00", "2026-08-04T08:56:00-03:00")


def _resolved_1h():
    return _make_resolved("2026-08-04T07:56:00-03:00", "2026-08-04T08:56:00-03:00")


def _resolved_1d():
    return _make_resolved("2026-08-03T08:56:00-03:00", "2026-08-04T08:56:00-03:00")


def _resolved_yesterday_today():
    return _make_resolved("2026-08-03T00:00:00-03:00", "2026-08-04T00:00:00-03:00")


def _resolved_iso():
    return _make_resolved("2026-08-03T10:00:00-03:00", "2026-08-04T10:00:00-03:00")


def _resolved_iso_positive_offset():
    return _make_resolved("2026-08-03T13:00:00+00:00", "2026-08-04T13:00:00+00:00")


class TestAnalyzeTimeNormalization:
    """analyze_pi_tag_behavior accepts PI time tokens."""

    def test_star_24h(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_24h(),
        ) as mock_resolve, patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_collected_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="LFS_RB2_AC_MA_VIB_VEL",
                start_time="*-24h",
                end_time="*",
                zero_policy="suspicious",
            ))
            mock_resolve.assert_called_once_with("*-24h", "*")
            assert isinstance(result, str)
            assert "LFS_RB2_AC_MA_VIB_VEL" in result

    def test_star_1h(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_1h(),
        ) as mock_resolve, patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_collected_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="LFS_RB2_AC_MA_VIB_VEL",
                start_time="*-1h",
                end_time="*",
                zero_policy="suspicious",
            ))
            mock_resolve.assert_called_once_with("*-1h", "*")
            assert isinstance(result, str)

    def test_star_1d(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_1d(),
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_collected_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="LFS_RB2_AC_MA_VIB_VEL",
                start_time="*-1d",
                end_time="*",
                zero_policy="suspicious",
            ))
            assert isinstance(result, str)

    def test_y_to_t(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_yesterday_today(),
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_collected_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="LFS_RB2_AC_MA_VIB_VEL",
                start_time="Y",
                end_time="T",
                zero_policy="suspicious",
            ))
            assert isinstance(result, str)

    def test_iso_aware_negative_offset(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_iso(),
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_collected_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="LFS_RB2_AC_MA_VIB_VEL",
                start_time="2026-08-03T10:00:00-03:00",
                end_time="2026-08-04T10:00:00-03:00",
                zero_policy="suspicious",
            ))
            assert isinstance(result, str)

    def test_iso_aware_positive_offset(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_iso_positive_offset(),
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_collected_data())
            result = asyncio.run(analyze_pi_tag_behavior(
                tag="LFS_RB2_AC_MA_VIB_VEL",
                start_time="2026-08-03T13:00:00+00:00",
                end_time="2026-08-04T13:00:00+00:00",
                zero_policy="suspicious",
            ))
            assert isinstance(result, str)

    def test_malformed_token_returns_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from fastmcp.exceptions import ToolError
        from domain.shared.errors import DomainValidationError, ValidationErrorCode

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=DomainValidationError(
                ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION,
                "Token não suportado.",
            ),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="T", start_time="*-abc", end_time="*", zero_policy="suspicious"
                ))

    def test_inverted_window_preserved(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior
        from fastmcp.exceptions import ToolError
        from domain.shared.errors import DomainValidationError, ValidationErrorCode

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=DomainValidationError(
                ValidationErrorCode.INVALID_TIME_WINDOW,
                "start_time deve ser anterior a end_time.",
            ),
        ):
            with pytest.raises(ToolError, match="INVALID_TIME_WINDOW"):
                asyncio.run(analyze_pi_tag_behavior(
                    tag="T", start_time="2026-08-04T00:00:00-03:00",
                    end_time="2026-08-03T00:00:00-03:00", zero_policy="suspicious"
                ))

    def test_single_resolve_call(self):
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_24h(),
        ) as mock_resolve, patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_one = AsyncMock(return_value=_make_collected_data())
            asyncio.run(analyze_pi_tag_behavior(
                tag="T", start_time="*-24h", end_time="*", zero_policy="suspicious"
            ))
            assert mock_resolve.call_count == 1

    def test_domain_still_strict(self):
        from domain.analysis.policies import _parse_iso
        from domain.shared.errors import DomainValidationError

        with pytest.raises(DomainValidationError):
            _parse_iso("*-24h", "start_time")


class TestReportTimeNormalization:
    """generate_pi_tags_analysis_report accepts PI time tokens."""

    def test_star_24h(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_24h(),
        ) as mock_resolve, patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_many = AsyncMock(
                return_value={"T1": _make_collected_data()}
            )
            with patch(
                "mcp_server.services.analysis_tools.XlsxReportBuilder"
            ) as MockBuilder, patch(
                "mcp_server.services.analysis_tools.DefaultDrivePublisher"
            ) as MockPublisher:
                mock_path = MagicMock()
                mock_path.read_bytes.return_value = b"\x00"
                MockBuilder.return_value.build_xlsx.return_value = mock_path
                mock_published = MagicMock()
                mock_published.name = "report.xlsx"
                mock_published.mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                mock_published.size_bytes = 100
                mock_published.view_url = "https://drive.google.com/test"
                MockPublisher.return_value.publish.return_value = mock_published
                result = asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T1"], start_time="*-24h", end_time="*", zero_policy="invalid"
                ))
                mock_resolve.assert_called_once_with("*-24h", "*")
                assert isinstance(result, str)

    def test_partial_success(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from domain.analysis.models import AnalysisError

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_24h(),
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_many = AsyncMock(
                return_value={
                    "T1": _make_collected_data(),
                    "T2": AnalysisError(tag="T2", code="TAG_NOT_FOUND", message="not found", retryable=False),
                }
            )
            with patch(
                "mcp_server.services.analysis_tools.XlsxReportBuilder"
            ) as MockBuilder, patch(
                "mcp_server.services.analysis_tools.DefaultDrivePublisher"
            ) as MockPublisher:
                mock_path = MagicMock()
                mock_path.read_bytes.return_value = b"\x00"
                MockBuilder.return_value.build_xlsx.return_value = mock_path
                mock_published = MagicMock()
                mock_published.name = "report.xlsx"
                mock_published.mime_type = "text/csv"
                mock_published.size_bytes = 100
                mock_published.view_url = "https://drive.google.com/test"
                MockPublisher.return_value.publish.return_value = mock_published
                result = asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T1", "T2"], start_time="*-24h", end_time="*", zero_policy="invalid"
                ))
                manifest = json.loads(result)
                assert manifest["status"] == "partial_success"

    def test_request_summary_normalized(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_24h(),
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_many = AsyncMock(
                return_value={"T1": _make_collected_data()}
            )
            with patch(
                "mcp_server.services.analysis_tools.XlsxReportBuilder"
            ) as MockBuilder, patch(
                "mcp_server.services.analysis_tools.DefaultDrivePublisher"
            ) as MockPublisher:
                mock_path = MagicMock()
                mock_path.read_bytes.return_value = b"\x00"
                MockBuilder.return_value.build_xlsx.return_value = mock_path
                mock_published = MagicMock()
                mock_published.name = "report.xlsx"
                mock_published.mime_type = "text/csv"
                mock_published.size_bytes = 100
                mock_published.view_url = "https://drive.google.com/test"
                MockPublisher.return_value.publish.return_value = mock_published
                result = asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T1"], start_time="*-24h", end_time="*", zero_policy="invalid"
                ))
                manifest = json.loads(result)
                req = manifest.get("request_summary", {})
                assert req.get("start_time") == "2026-08-03T08:56:00-03:00"
                assert req.get("end_time") == "2026-08-04T08:56:00-03:00"

    def test_same_period_for_all_tags(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            return_value=_resolved_24h(),
        ), patch(
            "mcp_server.services.analysis_tools.PiDataCollector"
        ) as MockCollector:
            MockCollector.return_value.fetch_many = AsyncMock(
                return_value={
                    "T1": _make_collected_data(),
                    "T2": _make_collected_data(),
                }
            )
            with patch(
                "mcp_server.services.analysis_tools.XlsxReportBuilder"
            ) as MockBuilder, patch(
                "mcp_server.services.analysis_tools.DefaultDrivePublisher"
            ) as MockPublisher:
                mock_path = MagicMock()
                mock_path.read_bytes.return_value = b"\x00"
                MockBuilder.return_value.build_xlsx.return_value = mock_path
                mock_published = MagicMock()
                mock_published.name = "report.xlsx"
                mock_published.mime_type = "text/csv"
                mock_published.size_bytes = 100
                mock_published.view_url = "https://drive.google.com/test"
                MockPublisher.return_value.publish.return_value = mock_published
                asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T1", "T2"], start_time="*-24h", end_time="*", zero_policy="invalid"
                ))
                call_args = MockCollector.return_value.fetch_many.call_args
                # fetch_many receives (tags, start_iso, end_iso) — start and end are different
                assert call_args[0][1] == "2026-08-03T08:56:00-03:00"  # start_iso
                assert call_args[0][2] == "2026-08-04T08:56:00-03:00"  # end_iso

    def test_invalid_token_returns_invalid_timestamp(self):
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from fastmcp.exceptions import ToolError
        from domain.shared.errors import DomainValidationError, ValidationErrorCode

        with patch(
            "mcp_server.services.analysis_tools.resolve_pi_time_range",
            side_effect=DomainValidationError(
                ValidationErrorCode.UNSUPPORTED_TIME_EXPRESSION,
                "Token não suportado.",
            ),
        ):
            with pytest.raises(ToolError, match="INVALID_TIMESTAMP"):
                asyncio.run(generate_pi_tags_analysis_report(
                    tags=["T"], start_time="*-abc", end_time="*", zero_policy="invalid"
                ))
