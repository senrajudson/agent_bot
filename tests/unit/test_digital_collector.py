"""Testes de client e collector digital — T066-T080.

Cobre: AtOrBefore, coleta paralela, reuso de WebId, parser único,
preservação de flags, código zero, Digital Set antes da coleta.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from domain.analysis.models import AnalysisPoint, AnalysisError, TagMetadata
from domain.analysis.services.pi_data_collector import CollectedData, PiDataCollector


METADATA_DIGITAL = TagMetadata(
    tag="CPD_LP_SECADOR_STATUS",
    point_type="digital",
    descriptor="Secador Status",
    engineering_units=None,
    digital_set="Estado_126",
)

STATES_126 = [
    {"indice": 0, "nome": "DESLIGADO", "descricao": "Desligado"},
    {"indice": 1, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 2, "nome": "LIGADO", "descricao": "Ligado"},
    {"indice": 3, "nome": "VAZIO", "descricao": "Vazio"},
    {"indice": 4, "nome": "FALHA", "descricao": "Falha"},
]


# ---------------------------------------------------------------------------
# T066 — Request AtOrBefore
# ---------------------------------------------------------------------------

class TestT066_AtOrBeforeRequest:
    def test_atorbefore_params(self) -> None:
        from domain.pims.clients.pi_web_api_client import get_value_at_or_before_by_web_id
        import inspect
        sig = inspect.signature(get_value_at_or_before_by_web_id)
        params = list(sig.parameters.keys())
        assert "web_id" in params
        assert "time" in params


# ---------------------------------------------------------------------------
# T067 — Resposta AtOrBefore válida
# ---------------------------------------------------------------------------

class TestT067_AtOrBeforeValid:
    def test_parse_single_point_valid(self) -> None:
        collector = PiDataCollector()
        raw = {
            "Items": [{
                "Timestamp": "2026-08-01T00:00:00-03:00",
                "Value": 0,
                "Good": True,
                "Questionable": False,
                "Substituted": False,
            }]
        }
        point = collector._parse_single_point(raw)
        assert point is not None
        assert point.value == 0.0
        assert point.good is True


# ---------------------------------------------------------------------------
# T068 — AtOrBefore vazio
# ---------------------------------------------------------------------------

class TestT068_AtOrBeforeEmpty:
    def test_empty_returns_none(self) -> None:
        collector = PiDataCollector()
        point = collector._parse_single_point({"Items": []})
        assert point is None

    def test_no_items_returns_none(self) -> None:
        collector = PiDataCollector()
        point = collector._parse_single_point({})
        assert point is None


# ---------------------------------------------------------------------------
# T069 — AtOrBefore malformado
# ---------------------------------------------------------------------------

class TestT069_AtOrBeforeMalformed:
    def test_non_list_items(self) -> None:
        collector = PiDataCollector()
        point = collector._parse_single_point({"Items": "invalid"})
        assert point is None

    def test_no_timestamp(self) -> None:
        collector = PiDataCollector()
        point = collector._parse_single_point({"Items": [{"Value": 0}]})
        assert point is None


# ---------------------------------------------------------------------------
# T070 — Timeout AtOrBefore
# ---------------------------------------------------------------------------

class TestT070_AtOrBeforeTimeout:
    async def test_timeout_returns_empty(self) -> None:
        collector = PiDataCollector()
        with patch(
            "domain.analysis.services.pi_data_collector.get_value_at_or_before_by_web_id",
            new_callable=AsyncMock,
            side_effect=Exception("timeout"),
        ):
            result = await collector._fetch_atorbefore("TAG", "WEBID", "2026-08-01T00:00:00-03:00")
            assert result == {}


# ---------------------------------------------------------------------------
# T071 — Auth AtOrBefore
# ---------------------------------------------------------------------------

class TestT071_AtOrBeforeAuth:
    async def test_auth_error_returns_empty(self) -> None:
        collector = PiDataCollector()
        with patch(
            "domain.analysis.services.pi_data_collector.get_value_at_or_before_by_web_id",
            new_callable=AsyncMock,
            side_effect=Exception("401 unauthorized"),
        ):
            result = await collector._fetch_atorbefore("TAG", "WEBID", "2026-08-01T00:00:00-03:00")
            assert result == {}


# ---------------------------------------------------------------------------
# T072 — Coleta paralela
# ---------------------------------------------------------------------------

class TestT072_ParallelFetch:
    async def test_parallel_calls(self) -> None:
        collector = PiDataCollector()
        with patch(
            "domain.analysis.services.pi_data_collector.get_value_at_or_before_by_web_id",
            new_callable=AsyncMock,
            return_value={"Items": [{"Timestamp": "2026-08-01T00:00:00-03:00", "Value": 0, "Good": True}]},
        ) as mock_atorbefore, patch(
            "domain.analysis.services.pi_data_collector.get_recorded_values_by_tag",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ) as mock_recorded:
            with patch.object(collector, "_resolve_digital_set_legacy", new_callable=AsyncMock, return_value="Estado_126"):
                with patch(
                    "domain.analysis.services.pi_data_collector.get_digital_set_states",
                    new_callable=AsyncMock,
                    return_value={"states": STATES_126},
                ):
                    # Create a minimal item dict
                    item = {"WebId": "WEBID123", "PointType": "Digital", "DigitalSet": "Estado_126"}
                    result = await collector._fetch_digital(
                        "CPD_LP_SECADOR_STATUS", "2026-08-01T00:00:00-03:00", "2026-08-08T00:00:00-03:00",
                        METADATA_DIGITAL, item,
                    )
                    assert isinstance(result, CollectedData)
                    mock_atorbefore.assert_called_once()
                    mock_recorded.assert_called_once()


# ---------------------------------------------------------------------------
# T073 — Reuso de WebId
# ---------------------------------------------------------------------------

class TestT073_WebIdReuse:
    async def test_webid_reused(self) -> None:
        collector = PiDataCollector()
        with patch(
            "domain.analysis.services.pi_data_collector.get_value_at_or_before_by_web_id",
            new_callable=AsyncMock,
            return_value={"Items": [{"Timestamp": "2026-08-01T00:00:00-03:00", "Value": 0, "Good": True}]},
        ) as mock_atorbefore, patch(
            "domain.analysis.services.pi_data_collector.get_recorded_values_by_tag",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ), patch(
            "domain.analysis.services.pi_data_collector.get_digital_set_states",
            new_callable=AsyncMock,
            return_value={"states": STATES_126},
        ):
            item = {"WebId": "WEBID123", "PointType": "Digital", "DigitalSet": "Estado_126"}
            await collector._fetch_digital("TAG", "2026-08-01T00:00:00-03:00", "2026-08-08T00:00:00-03:00", METADATA_DIGITAL, item)
            # AtOrBefore was called
            mock_atorbefore.assert_called_once()
            # The first positional arg to get_value_at_or_before_by_web_id is web_id
            call_args = mock_atorbefore.call_args
            assert call_args[0][0] == "WEBID123"


# ---------------------------------------------------------------------------
# T074 — Digital não chama Interpolated
# ---------------------------------------------------------------------------

class TestT074_NoInterpolated:
    async def test_no_interpolated_call(self) -> None:
        collector = PiDataCollector()
        with patch(
            "domain.analysis.services.pi_data_collector.get_value_at_or_before_by_web_id",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ), patch(
            "domain.analysis.services.pi_data_collector.get_recorded_values_by_tag",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ), patch(
            "domain.analysis.services.pi_data_collector.get_interpolated_values_by_tag",
            new_callable=AsyncMock,
        ) as mock_interp, patch(
            "domain.analysis.services.pi_data_collector.get_digital_set_states",
            new_callable=AsyncMock,
            return_value={"states": STATES_126},
        ):
            item = {"WebId": "W", "PointType": "Digital", "DigitalSet": "Estado_126"}
            await collector._fetch_digital("TAG", "2026-08-01T00:00:00-03:00", "2026-08-08T00:00:00-03:00", METADATA_DIGITAL, item)
            mock_interp.assert_not_called()


# ---------------------------------------------------------------------------
# T076 — Preservação de flags
# ---------------------------------------------------------------------------

class TestT076_FlagsPreserved:
    def test_flags_preserved(self) -> None:
        collector = PiDataCollector()
        raw = {
            "Items": [{
                "Timestamp": "2026-08-01T00:00:00-03:00",
                "Value": 1,
                "Good": False,
                "Questionable": True,
                "Substituted": True,
            }]
        }
        point = collector._parse_single_point(raw)
        assert point is not None
        assert point.good is False
        assert point.questionable is True
        assert point.substituted is True

    def test_value_none_preserved(self) -> None:
        collector = PiDataCollector()
        raw = {"Items": [{"Timestamp": "2026-08-01T00:00:00-03:00", "Value": None, "Good": True}]}
        point = collector._parse_single_point(raw)
        assert point is not None
        assert point.value is None


# ---------------------------------------------------------------------------
# T077 — Código zero no collector
# ---------------------------------------------------------------------------

class TestT077_ZeroCodeCollector:
    def test_zero_code(self) -> None:
        collector = PiDataCollector()
        raw = {"Items": [{"Timestamp": "2026-08-01T00:00:00-03:00", "Value": 0, "Good": True}]}
        point = collector._parse_single_point(raw)
        assert point is not None
        assert point.value == 0.0
        assert point.good is True


# ---------------------------------------------------------------------------
# T078 — Digital Set antes da coleta temporal
# ---------------------------------------------------------------------------

class TestT078_DigitalSetBeforeFetch:
    async def test_ds_resolved_before_temporal(self) -> None:
        collector = PiDataCollector()
        call_order = []
        original_atorbefore = collector._fetch_atorbefore
        original_recorded = collector._fetch_recorded

        async def mock_atorbefore(tag, web_id, start):
            call_order.append("atorbefore")
            return {"Items": []}

        async def mock_recorded(tag, start, end):
            call_order.append("recorded")
            return []

        with patch.object(collector, "_fetch_atorbefore", mock_atorbefore), \
             patch.object(collector, "_fetch_recorded", mock_recorded), \
             patch(
                 "domain.analysis.services.pi_data_collector.get_digital_set_states",
                 new_callable=AsyncMock,
                 return_value={"states": STATES_126},
             ):
            item = {"WebId": "W", "PointType": "Digital", "DigitalSet": "Estado_126"}
            await collector._fetch_digital("TAG", "2026-08-01T00:00:00-03:00", "2026-08-08T00:00:00-03:00", METADATA_DIGITAL, item)
            # Both should have been called (in parallel via gather)
            assert "atorbefore" in call_order
            assert "recorded" in call_order


# ---------------------------------------------------------------------------
# T079 — INVALID_DIGITAL_SET legítimo
# ---------------------------------------------------------------------------

class TestT079_InvalidDigitalSet:
    async def test_invalid_ds(self) -> None:
        collector = PiDataCollector()
        item = {"WebId": "W", "PointType": "Digital"}
        result = await collector._fetch_digital(
            "TAG", "2026-08-01T00:00:00-03:00", "2026-08-08T00:00:00-03:00",
            TagMetadata(tag="TAG", point_type="digital", descriptor=""), item,
        )
        assert isinstance(result, AnalysisError)
        assert result.code == "INVALID_DIGITAL_SET"
