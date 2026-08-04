from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from domain.analysis.models import AnalysisPoint, TagMetadata
from domain.analysis.services.pi_data_collector import CollectedData
from mcp_server.services.delivery.drive_publisher import PublishedArtifact


MOCK_METADATA = TagMetadata(tag="LFI_TEST", point_type="numeric", descriptor="Test", engineering_units="Nm3/h")


class TestGeneratePiTagsAnalysisReport:
    def test_all_failed_no_manifest(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from domain.analysis.models import AnalysisError

        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector:
            MockCollector.return_value.fetch_many = AsyncMock(return_value={
                "FAIL1": AnalysisError(tag="FAIL1", code="PI_TIMEOUT", message="t1", retryable=True),
                "FAIL2": AnalysisError(tag="FAIL2", code="TAG_NOT_FOUND", message="t2", retryable=False),
            })
            import asyncio
            with pytest.raises(Exception, match="PI_SERIES_QUERY_ERROR"):
                asyncio.run(generate_pi_tags_analysis_report(
                    tags=["FAIL1", "FAIL2"],
                    start_time="2026-01-01T00:00:00-03:00",
                    end_time="2026-01-01T01:00:00-03:00",
                ))

    def test_partial_success(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report
        from domain.analysis.models import AnalysisError

        ok_data = CollectedData(
            metadata=MOCK_METADATA,
            recorded=[AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0)],
            interpolated=[AnalysisPoint(timestamp="2026-01-01T00:00:00-03:00", value=10.0)],
        )
        error = AnalysisError(tag="FAIL", code="PI_TIMEOUT", message="timeout", retryable=True)

        with patch("mcp_server.services.analysis_tools.PiDataCollector") as MockCollector, \
             patch("mcp_server.services.analysis_tools.DefaultDrivePublisher") as MockPublisher, \
             patch("mcp_server.clients.google_drive_client.GoogleDriveClient"):
            MockCollector.return_value.fetch_many = AsyncMock(return_value={
                "OK": ok_data, "FAIL": error,
            })
            MockPublisher.return_value.publish = MagicMock(return_value=PublishedArtifact(
                name="test.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size_bytes=1000,
                view_url="https://drive.google.com/file/d/xxx/view",
            ))
            import asyncio
            result = asyncio.run(generate_pi_tags_analysis_report(
                tags=["OK", "FAIL"],
                start_time="2026-01-01T00:00:00-03:00",
                end_time="2026-01-01T01:00:00-03:00",
            ))

        assert isinstance(result, str)
        import json
        manifest = json.loads(result)
        assert manifest["status"] == "partial_success"
        assert manifest["delivery"] == "drive_artifact"
        assert manifest["tool_name"] == "generate_pi_tags_analysis_report"
        assert "view_url" in manifest["artifact"]

    def test_invalid_timestamp(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report

        import asyncio
        with pytest.raises(Exception, match="INVALID_TIMESTAMP"):
            asyncio.run(generate_pi_tags_analysis_report(
                tags=["X"],
                start_time="not-a-date",
                end_time="2026-01-02T00:00:00-03:00",
            ))

    def test_too_many_tags(self) -> None:
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report

        tags = [f"TAG_{i}" for i in range(11)]
        import asyncio
        with pytest.raises(Exception, match="TOO_MANY_TAGS"):
            asyncio.run(generate_pi_tags_analysis_report(
                tags=tags,
                start_time="2026-01-01T00:00:00-03:00",
                end_time="2026-01-02T00:00:00-03:00",
            ))
