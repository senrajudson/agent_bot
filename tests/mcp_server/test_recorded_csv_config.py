"""Testes de configuração para MCP_SERIES_CSV_RECORDED_MAX_COUNT.

Valida:
- T003: Default sem ENV é 150000
- T004: Override via ENV preservado
- T005: Ausência de cap/clamp
- T010: Propagação do default 150000 ao client
- T011: Propagação de valor sentinela ao client
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_MCP_ROOT = Path(__file__).parent.parent.parent / "mcp_server"
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
if str(_MCP_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT.parent))

import pytest


class TestRecordedCsvDefault:
    """T003: Default sem ENV é 150000."""

    def test_default_without_env(self):
        from core.config import Settings

        s = Settings(_env_file=None)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT == 150_000

    def test_default_is_positive(self):
        from core.config import Settings

        s = Settings(_env_file=None)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT > 0


class TestRecordedCsvEnvOverride:
    """T004: Override via ENV preservado."""

    def test_override_100000(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_SERIES_CSV_RECORDED_MAX_COUNT=100000)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT == 100000

    def test_override_150000(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_SERIES_CSV_RECORDED_MAX_COUNT=150000)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT == 150000

    def test_override_200000(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_SERIES_CSV_RECORDED_MAX_COUNT=200000)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT == 200000

    def test_override_250000(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_SERIES_CSV_RECORDED_MAX_COUNT=250000)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT == 250000


class TestRecordedCsvNoCap:
    """T005: Ausência de cap/clamp."""

    def test_large_positive_value_not_clamped(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_SERIES_CSV_RECORDED_MAX_COUNT=300000)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT == 300000

    def test_very_large_value_not_clamped(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_SERIES_CSV_RECORDED_MAX_COUNT=999999)
        assert s.MCP_SERIES_CSV_RECORDED_MAX_COUNT == 999999

    def test_zero_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=True,
                GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
                GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
                MCP_SERIES_CSV_RECORDED_MAX_COUNT=0,
            )

    def test_negative_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=True,
                GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=__file__,
                GOOGLE_DRIVE_EXPORT_FOLDER_ID="folder1",
                MCP_SERIES_CSV_RECORDED_MAX_COUNT=-1,
            )


class TestRecordedCsvPropagation:
    """T010-T011: Propagação do maxCount ao client PI."""

    @pytest.mark.asyncio
    async def test_default_150000_propagated(self):
        """T010: Service sem override propaga 150000 ao client."""
        from domain.pims.services.generate_pi_tags_series_csv_service import (
            generate_pi_tags_series_csv_service,
        )

        call_kwargs = {}

        async def mock_get_recorded(tag, **kwargs):
            call_kwargs.update(kwargs)
            return {"Items": [], "PointType": "Analog"}

        with patch(
            "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
            side_effect=mock_get_recorded,
        ), patch(
            "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
            new_callable=AsyncMock,
            return_value={"PointType": "Analog", "EngineeringUnits": ""},
        ):
            await generate_pi_tags_series_csv_service(
                tags=["TEST_TAG"],
                start_time="*-1h",
                end_time="*",
                data_method="recorded",
            )

        assert call_kwargs.get("max_count") == 150_000

    @pytest.mark.asyncio
    async def test_sentinel_12345_propagated(self):
        """T011: Override explícito chega intacto ao client."""
        from domain.pims.services.generate_pi_tags_series_csv_service import (
            generate_pi_tags_series_csv_service,
        )

        call_kwargs = {}

        async def mock_get_recorded(tag, **kwargs):
            call_kwargs.update(kwargs)
            return {"Items": [], "PointType": "Analog"}

        with patch(
            "domain.pims.services.generate_pi_tags_series_csv_service.get_recorded_values_by_tag",
            side_effect=mock_get_recorded,
        ), patch(
            "domain.pims.services.generate_pi_tags_series_csv_service.get_point_by_tag",
            new_callable=AsyncMock,
            return_value={"PointType": "Analog", "EngineeringUnits": ""},
        ):
            await generate_pi_tags_series_csv_service(
                tags=["TEST_TAG"],
                start_time="*-1h",
                end_time="*",
                data_method="recorded",
                recorded_max_count=12345,
            )

        assert call_kwargs.get("max_count") == 12345


class TestAnalysisRecordedDefault:
    """T011: Default sem ENV é 150000 para analysis."""

    def test_default_without_env(self):
        from core.config import Settings

        s = Settings(_env_file=None)
        assert s.MCP_ANALYSIS_RECORDED_MAX_COUNT == 150_000

    def test_default_is_positive(self):
        from core.config import Settings

        s = Settings(_env_file=None)
        assert s.MCP_ANALYSIS_RECORDED_MAX_COUNT > 0


class TestAnalysisRecordedEnvOverride:
    """T011: Override via ENV preservado para analysis."""

    def test_override_100000(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_ANALYSIS_RECORDED_MAX_COUNT=100000)
        assert s.MCP_ANALYSIS_RECORDED_MAX_COUNT == 100000

    def test_override_12345(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_ANALYSIS_RECORDED_MAX_COUNT=12345)
        assert s.MCP_ANALYSIS_RECORDED_MAX_COUNT == 12345

    def test_override_150000(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_ANALYSIS_RECORDED_MAX_COUNT=150000)
        assert s.MCP_ANALYSIS_RECORDED_MAX_COUNT == 150000

    def test_override_250000(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_ANALYSIS_RECORDED_MAX_COUNT=250000)
        assert s.MCP_ANALYSIS_RECORDED_MAX_COUNT == 250000


class TestAnalysisRecordedNoCap:
    """T011: Ausência de cap/clamp para analysis."""

    def test_large_positive_value_not_clamped(self):
        from core.config import Settings

        s = Settings(_env_file=None, MCP_ANALYSIS_RECORDED_MAX_COUNT=300000)
        assert s.MCP_ANALYSIS_RECORDED_MAX_COUNT == 300000

    def test_zero_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                MCP_ANALYSIS_RECORDED_MAX_COUNT=0,
            )

    def test_negative_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                MCP_ANALYSIS_RECORDED_MAX_COUNT=-100,
            )
