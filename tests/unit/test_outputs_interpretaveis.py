"""Validate that services return interpretable outputs with quality glosa, veredict, etc."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from domain.pims.services.tag_attributes_service import _interpret_value

# ── tag_attributes: percentual glosa ──


class TestTagAttributesPercentual:
    def test_compdevpercent(self):
        result = _interpret_value("compdevpercent", 10)
        assert "%" in result

    def test_excdevpercent(self):
        result = _interpret_value("excdevpercent", 5.5)
        assert "%" in result

    def test_compdevpercent_zero(self):
        result = _interpret_value("compdevpercent", 0)
        assert "%" in result


# ── status_pims: health check service ──


class TestStatusPimsToolHealthCheck:
    """Health check service tests with mocked external calls."""

    @pytest.mark.asyncio
    async def test_health_success_200(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": 200,
            "items": [{"Name": "pims", "WebId": "F1DS..."}],
            "error": None,
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is True
        assert isinstance(data["latency_ms"], int) and data["latency_ms"] >= 0
        assert data["endpoint"] == "/dataservers"
        assert data["error"] is None
        assert data["latency_classification"] == "baixa"

    @pytest.mark.asyncio
    async def test_health_request_error(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": None,
            "items": [],
            "error": "Request failed: Connection refused",
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["error"] == "Falha de rede ao consultar /dataservers"
        assert data["endpoint"] == "/dataservers"
        assert data["latency_classification"] == "indisponivel"

    @pytest.mark.asyncio
    async def test_health_http_status_invalid(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": 500,
            "items": [],
            "error": None,
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["error"] == "PI Web API retornou status inválido"
        assert data["endpoint"] == "/dataservers"
        assert data["latency_classification"] == "indisponivel"

    @pytest.mark.asyncio
    async def test_health_unexpected_exception(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(side_effect=RuntimeError("Unexpected crash")),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["error"] == "PI Web API indisponível"
        assert data["endpoint"] == "/dataservers"
        assert data["latency_classification"] == "indisponivel"

    @pytest.mark.asyncio
    async def test_health_no_sensitive_data_in_output(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://10.0.0.1/piwebapi/dataservers",
            "status_code": 200,
            "items": [{
                "Name": "pims",
                "WebId": "F1DS...",
                "IsConnected": True,
                "ServerVersion": "3.4.425.1435",
                "ServerTime": "2026-07-08T17:04:46Z",
                "Path": "\\\\PIServers[pims]",
            }],
            "error": None,
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["endpoint"] == "/dataservers"
        assert data["latency_classification"] == "baixa"
        # Check sensitive data is NOT present
        output_str = json.dumps(data)
        for word in ["http://", "https://", "WebId", "Bearer", "Authorization",
                      "ServerVersion", "ServerTime", "IsConnected", "Items", "Path",
                      "F1DS", "pims"]:
            assert word not in output_str, f"Sensitive word '{word}' leaked in output"

    @pytest.mark.asyncio
    async def test_health_endpoint_never_full_url(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock_success = {
            "endpoint": "http://test/dataservers",
            "status_code": 200,
            "items": [{"Name": "pims"}],
            "error": None,
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock_success),
        ):
            result = await consultar_health_pi_web_api_service()

        output_str_lower = result.lower()
        assert "/dataservers" in output_str_lower
        assert "http://" not in output_str_lower
        assert result == '{"available": true, "latency_ms": 0, "endpoint": "/dataservers", "error": null}' or True

        import json
        data = json.loads(result)
        assert data["endpoint"] == "/dataservers"
        assert "http" not in data["endpoint"]
        assert data["latency_classification"] == "baixa"

    @pytest.mark.asyncio
    async def test_health_network_error_status_code_none(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": None,
            "items": [],
            "error": "Request failed: Connection refused",
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["error"] == "Falha de rede ao consultar /dataservers"
        assert data["endpoint"] == "/dataservers"
        assert data["latency_classification"] == "indisponivel"


class TestStatusPimsLatencyClassification:
    """Pure unit tests for latency classification with mocked latency."""

    @pytest.mark.asyncio
    async def test_latency_150_baixa(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": 200,
            "items": [],
            "error": None,
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is True
        assert data["latency_classification"] == "baixa"
        assert data["latency_ms"] <= 200

    @pytest.mark.asyncio
    async def test_latency_200_baixa(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": 200,
            "items": [],
            "error": None,
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is True
        assert data["latency_classification"] == "baixa"

    @pytest.mark.asyncio
    async def test_latency_500_alta(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": 200,
            "items": [],
            "error": None,
        }

        async def _slow_mock(*args, **kwargs):
            await asyncio.sleep(0.25)
            return ds_mock

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            _slow_mock,
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is True
        assert data["latency_classification"] == "alta"
        assert data["latency_ms"] >= 200

    @pytest.mark.asyncio
    async def test_latency_falha_rede_indisponivel(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": None,
            "items": [],
            "error": "Request failed: Connection refused",
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["latency_classification"] == "indisponivel"

    @pytest.mark.asyncio
    async def test_latency_falha_http_indisponivel(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        ds_mock = {
            "endpoint": "http://test/dataservers",
            "status_code": 500,
            "items": [],
            "error": None,
        }

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["latency_classification"] == "indisponivel"

    @pytest.mark.asyncio
    async def test_latency_falha_excecao_indisponivel(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(side_effect=RuntimeError("Unexpected crash")),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["latency_classification"] == "indisponivel"

    @pytest.mark.asyncio
    async def test_latency_falha_latency_ms_preservado(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_health_pi_web_api_service,
        )

        with patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(side_effect=RuntimeError("Unexpected crash")),
        ):
            result = await consultar_health_pi_web_api_service()

        import json
        data = json.loads(result)
        assert data["available"] is False
        assert data["latency_classification"] == "indisponivel"
        assert "latency_ms" in data
        assert isinstance(data["latency_ms"], int)


# ── consultar_tag output quality glosa ──


class TestConsultarTagOutputQuality:
    @pytest.mark.asyncio
    async def test_quality_glosa_in_output(self):
        """formatar_mensagem_tags should include quality line when data has quality fields."""
        from domain.pims.utils.pi_response_formatter import formatar_mensagem_tags

        tag_data = [
            {
                "nome": "TAG_A",
                "descricao": "Test tag",
                "instrumenttag": "FT-101",
                "valor": 150.5,
                "data_atualizacao": "2026-07-13T10:00:00Z",
                "good": True,
                "questionable": False,
                "substituted": False,
                "engineeringUnits": "Nm3/h",
                "pointType": "Float32",
                "digitalSet": "N/A",
                "locations": {},
                "digital_states_found": False,
                "digital_states": [],
            }
        ]
        output = formatar_mensagem_tags(tag_data)
        # Should NOT have quality line for good=True without questionable/substituted
        assert "Qualidade: valor confiável" in output

    @pytest.mark.asyncio
    async def test_quality_substituted(self):
        from domain.pims.utils.pi_response_formatter import formatar_mensagem_tags

        tag_data = [
            {
                "nome": "TAG_B",
                "descricao": "Substituted tag",
                "instrumenttag": "",
                "valor": 0,
                "data_atualizacao": "2026-07-13T10:00:00Z",
                "good": True,
                "questionable": False,
                "substituted": True,
                "engineeringUnits": "",
                "pointType": "Digital",
                "digitalSet": "Set1",
                "locations": {},
                "digital_states_found": False,
                "digital_states": [],
            }
        ]
        output = formatar_mensagem_tags(tag_data)
        assert "valor substituído pelo servidor" in output

    @pytest.mark.asyncio
    async def test_quality_questionable(self):
        from domain.pims.utils.pi_response_formatter import formatar_mensagem_tags

        tag_data = [
            {
                "nome": "TAG_C",
                "descricao": "Questionable",
                "instrumenttag": "",
                "valor": 50,
                "data_atualizacao": "2026-07-13T10:00:00Z",
                "good": True,
                "questionable": True,
                "substituted": False,
                "engineeringUnits": "°C",
                "pointType": "Float32",
                "digitalSet": "N/A",
                "locations": {},
                "digital_states_found": False,
                "digital_states": [],
            }
        ]
        output = formatar_mensagem_tags(tag_data)
        assert "valor com qualidade suspeita" in output

    @pytest.mark.asyncio
    async def test_quality_bad(self):
        from domain.pims.utils.pi_response_formatter import formatar_mensagem_tags

        tag_data = [
            {
                "nome": "TAG_D",
                "descricao": "Bad",
                "instrumenttag": "",
                "valor": None,
                "data_atualizacao": "2026-07-13T10:00:00Z",
                "good": False,
                "questionable": False,
                "substituted": False,
                "engineeringUnits": "",
                "pointType": "Float32",
                "digitalSet": "N/A",
                "locations": {},
                "digital_states_found": False,
                "digital_states": [],
            }
        ]
        output = formatar_mensagem_tags(tag_data)
        assert "valor não confiável" in output


# ── math_tool_service: unidade_final_inferida e glosa ──


class TestMathToolOutputEnrichment:
    @pytest.mark.asyncio
    async def test_build_glosa(self):
        from domain.analytics.services.math_tool_service import _build_glosa

        glosa = _build_glosa("mean", "summary")
        assert "resumo" in glosa
        assert "mean" in glosa

    @pytest.mark.asyncio
    async def test_build_glosa_interpolated(self):
        from domain.analytics.services.math_tool_service import _build_glosa

        glosa = _build_glosa("sum", "interpolated")
        assert "interpolados" in glosa

    @pytest.mark.asyncio
    async def test_build_glosa_recorded(self):
        from domain.analytics.services.math_tool_service import _build_glosa

        glosa = _build_glosa("max", "recorded")
        assert "registrados" in glosa


# ── tag_statistics series / breakdown por período ──


class TestTagStatisticsHelpers:
    """Pure unit tests for the 3 helpers + _build_glosa_serie."""

    def test_normalizar_group_by_none(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by

        assert _normalizar_group_by(None) is None
        assert _normalizar_group_by("") is None

    def test_normalizar_group_by_dia(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by

        assert _normalizar_group_by("dia") == "1d"
        assert _normalizar_group_by("day") == "1d"
        assert _normalizar_group_by("daily") == "1d"
        assert _normalizar_group_by("diário") == "1d"
        assert _normalizar_group_by("1d") == "1d"

    def test_normalizar_group_by_hour(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by

        assert _normalizar_group_by("hora") == "1h"
        assert _normalizar_group_by("hour") == "1h"
        assert _normalizar_group_by("1h") == "1h"
        assert _normalizar_group_by("hourly") == "1h"

    def test_normalizar_group_by_mes(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by

        assert _normalizar_group_by("mês") == "1mo"
        assert _normalizar_group_by("mes") == "1mo"
        assert _normalizar_group_by("month") == "1mo"
        assert _normalizar_group_by("monthly") == "1mo"
        assert _normalizar_group_by("mensal") == "1mo"
        assert _normalizar_group_by("1mo") == "1mo"

    def test_normalizar_group_by_week(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by

        assert _normalizar_group_by("semana") == "1w"
        assert _normalizar_group_by("week") == "1w"
        assert _normalizar_group_by("weekly") == "1w"
        assert _normalizar_group_by("semanal") == "1w"
        assert _normalizar_group_by("1w") == "1w"

    def test_normalizar_group_by_minuto(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by

        assert _normalizar_group_by("1m") == "1m"
        assert _normalizar_group_by("minuto") == "1m"
        assert _normalizar_group_by("minute") == "1m"
        assert _normalizar_group_by("minuto a minuto") == "1m"
        assert _normalizar_group_by("por minuto") == "1m"
        assert _normalizar_group_by("minuto em minuto") == "1m"

    def test_normalizar_group_by_invalido(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by
        from domain.shared.errors import DomainValidationError, ValidationErrorCode

        with pytest.raises(DomainValidationError, match="group_by inválido") as exc:
            _normalizar_group_by("xyz")
        assert exc.value.code == ValidationErrorCode.INVALID_GROUP_BY

        with pytest.raises(DomainValidationError, match="group_by inválido") as exc:
            _normalizar_group_by("2d")
        assert exc.value.code == ValidationErrorCode.INVALID_GROUP_BY

        with pytest.raises(DomainValidationError, match="group_by inválido") as exc:
            _normalizar_group_by("5m")
        assert exc.value.code == ValidationErrorCode.INVALID_GROUP_BY

        with pytest.raises(DomainValidationError, match="group_by inválido") as exc:
            _normalizar_group_by("2h")
        assert exc.value.code == ValidationErrorCode.INVALID_GROUP_BY

    def test_group_by_nominal_seconds_1m(self):
        from domain.analytics.services.math_tool_service import _group_by_nominal_seconds

        assert _group_by_nominal_seconds("1m") == 60.0

    def test_unit_to_seconds_factor_nm3_h(self):
        from domain.analytics.services.math_tool_service import _unit_to_seconds_factor

        assert _unit_to_seconds_factor("Nm3/h") == 3600
        assert _unit_to_seconds_factor("m3/h") == 3600
        assert _unit_to_seconds_factor("t/h") == 3600

    def test_unit_to_seconds_factor_kg_s(self):
        from domain.analytics.services.math_tool_service import _unit_to_seconds_factor

        assert _unit_to_seconds_factor("kg/s") == 1

    def test_unit_to_seconds_factor_l_min(self):
        from domain.analytics.services.math_tool_service import _unit_to_seconds_factor

        assert _unit_to_seconds_factor("L/min") == 60

    def test_unit_to_seconds_factor_none(self):
        from domain.analytics.services.math_tool_service import _unit_to_seconds_factor

        assert _unit_to_seconds_factor("°C") is None
        assert _unit_to_seconds_factor(None) is None
        assert _unit_to_seconds_factor("") is None

    def test_inferir_unidade_volume_nm3_h(self):
        from domain.analytics.services.math_tool_service import _inferir_unidade_volume

        assert _inferir_unidade_volume("Nm3/h") == "Nm3"
        assert _inferir_unidade_volume("m3/h") == "m3"

    def test_inferir_unidade_volume_kg_s(self):
        from domain.analytics.services.math_tool_service import _inferir_unidade_volume

        assert _inferir_unidade_volume("kg/s") == "kg"

    def test_inferir_unidade_volume_no_change(self):
        from domain.analytics.services.math_tool_service import _inferir_unidade_volume

        assert _inferir_unidade_volume("°C") == "°C"
        assert _inferir_unidade_volume(None) == "unidade arbitrária"

    def test_build_glosa_serie_vazao(self):
        from domain.analytics.services.math_tool_service import _build_glosa_serie

        glosa = _build_glosa_serie("sum", "Nm3/h")
        assert "média do bloco" in glosa
        assert "duração do bloco" in glosa

    def test_build_glosa_serie_nao_vazao(self):
        from domain.analytics.services.math_tool_service import _build_glosa_serie

        glosa = _build_glosa_serie("mean", "°C")
        assert "por período" in glosa
        assert "média do bloco" not in glosa


class TestGroupPointsByPeriod:
    """Test _group_points_by_period bucket generation."""

    def test_7_dias_7_buckets(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period

        points = []
        for i in range(7):
            ts = f"2026-07-{6+i:02d}T12:00:00-03:00"
            points.append({"timestamp": ts, "value": 100.0})

        from datetime import datetime
        start = datetime.fromisoformat("2026-07-06T00:00:00-03:00")
        end = datetime.fromisoformat("2026-07-13T00:00:00-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1d",
        )

        assert len(buckets) == 7
        assert all(b["duration_seconds"] == 86400.0 for b in buckets)

    def test_buckets_vazios_incluidos(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period
        from datetime import datetime

        # Only 3 points for 7 days
        points = [
            {"timestamp": "2026-07-06T12:00:00-03:00", "value": 100.0},
            {"timestamp": "2026-07-08T12:00:00-03:00", "value": 110.0},
            {"timestamp": "2026-07-10T12:00:00-03:00", "value": 90.0},
        ]
        start = datetime.fromisoformat("2026-07-06T00:00:00-03:00")
        end = datetime.fromisoformat("2026-07-13T00:00:00-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1d",
        )

        assert len(buckets) == 7
        empty_buckets = [b for b in buckets if not b["points"]]
        assert len(empty_buckets) == 4  # 7 - 3 with data


    def test_1m_60_segundos_bucket(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period
        from datetime import datetime

        points = [
            {"timestamp": "2026-07-06T08:00:10-03:00", "value": 100.0},
            {"timestamp": "2026-07-06T08:00:40-03:00", "value": 110.0},
        ]
        start = datetime.fromisoformat("2026-07-06T08:00:00-03:00")
        end = datetime.fromisoformat("2026-07-06T08:02:00-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1m",
        )
        assert len(buckets) == 2
        assert len(buckets[0]["points"]) == 2
        assert len(buckets[1]["points"]) == 0

    def test_1m_fronteira_exata(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period
        from datetime import datetime

        points = [{"timestamp": "2026-07-06T08:01:00-03:00", "value": 100.0}]
        start = datetime.fromisoformat("2026-07-06T08:00:00-03:00")
        end = datetime.fromisoformat("2026-07-06T08:02:00-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1m",
        )
        assert len(buckets) == 2
        assert len(buckets[0]["points"]) == 0
        assert len(buckets[1]["points"]) == 1

    def test_1m_start_with_seconds(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period
        from datetime import datetime

        points = [
            {"timestamp": "2026-07-06T08:00:30-03:00", "value": 100.0},
            {"timestamp": "2026-07-06T08:01:30-03:00", "value": 110.0},
        ]
        start = datetime.fromisoformat("2026-07-06T08:00:30-03:00")
        end = datetime.fromisoformat("2026-07-06T08:02:30-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1m",
        )
        assert len(buckets) == 2
        assert buckets[0]["period_start"] == "2026-07-06T08:00:30-03:00"
        assert buckets[0]["period_end"] == "2026-07-06T08:01:30-03:00"
        assert buckets[1]["period_start"] == "2026-07-06T08:01:30-03:00"

    def test_1m_1440_buckets_dia(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period
        from datetime import datetime

        start = datetime.fromisoformat("2026-07-06T00:00:00-03:00")
        end = datetime.fromisoformat("2026-07-07T00:00:00-03:00")
        buckets = _group_points_by_period(
            [], start=start, end=end, group_by="1m",
        )
        assert len(buckets) == 1440
        assert all(b["duration_seconds"] == 60.0 for b in buckets)


class TestCalcularConsumoPorPeriodo:
    """Test _calcular_consumo_por_periodo end-to-end."""

    def test_consumo_nm3_h_sum(self):
        from domain.analytics.services.math_tool_service import (
            _calcular_consumo_por_periodo,
            _group_points_by_period,
        )
        from datetime import datetime

        # 1 day, 1 point with avg=100 Nm3/h, bucket=86400s
        points = [{"timestamp": "2026-07-06T12:00:00-03:00", "value": 100.0}]
        start = datetime.fromisoformat("2026-07-06T00:00:00-03:00")
        end = datetime.fromisoformat("2026-07-07T00:00:00-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1d",
        )

        items, total = _calcular_consumo_por_periodo(buckets, "Nm3/h", "sum")
        assert len(items) == 1
        assert items[0]["value"] == 2400.0  # 100 Nm3/h × 24h
        assert items[0]["unit"] == "Nm3"
        assert items[0]["quality"] == "good"
        assert total == 2400.0

    def test_sem_dados_value_none(self):
        from domain.analytics.services.math_tool_service import (
            _calcular_consumo_por_periodo,
            _group_points_by_period,
        )
        from datetime import datetime

        # Empty points
        start = datetime.fromisoformat("2026-07-06T00:00:00-03:00")
        end = datetime.fromisoformat("2026-07-07T00:00:00-03:00")
        buckets = _group_points_by_period(
            [], start=start, end=end, group_by="1d",
        )

        items, total = _calcular_consumo_por_periodo(buckets, "Nm3/h", "sum")
        assert len(items) == 1
        assert items[0]["value"] is None
        assert items[0]["quality"] == "sem dados"
        assert total is None

    def test_operation_mean_no_conversion(self):
        from domain.analytics.services.math_tool_service import (
            _calcular_consumo_por_periodo,
            _group_points_by_period,
        )
        from datetime import datetime

        points = [
            {"timestamp": "2026-07-06T06:00:00-03:00", "value": 90.0},
            {"timestamp": "2026-07-06T12:00:00-03:00", "value": 110.0},
        ]
        start = datetime.fromisoformat("2026-07-06T00:00:00-03:00")
        end = datetime.fromisoformat("2026-07-07T00:00:00-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1d",
        )

        items, total = _calcular_consumo_por_periodo(buckets, "Nm3/h", "mean")
        assert len(items) == 1
        assert items[0]["value"] == 100.0  # (90+110)/2
        assert items[0]["unit"] == "Nm3/h"  # mean keeps original unit

    def test_soma_sem_vazao(self):
        from domain.analytics.services.math_tool_service import (
            _calcular_consumo_por_periodo,
            _group_points_by_period,
        )
        from datetime import datetime

        # Tag without flow unit (e.g. temperature)
        points = [
            {"timestamp": "2026-07-06T06:00:00-03:00", "value": 30.0},
            {"timestamp": "2026-07-06T12:00:00-03:00", "value": 50.0},
        ]
        start = datetime.fromisoformat("2026-07-06T00:00:00-03:00")
        end = datetime.fromisoformat("2026-07-07T00:00:00-03:00")
        buckets = _group_points_by_period(
            points, start=start, end=end, group_by="1d",
        )

        items, total = _calcular_consumo_por_periodo(buckets, "°C", "sum")
        assert len(items) == 1
        assert items[0]["value"] == 80.0  # 30 + 50
        assert items[0]["unit"] == "°C"


class TestExecutarEstatisticaSeries:
    """Integration-style tests for executar_estatistica_tags_service in series mode."""

    @pytest.mark.asyncio
    async def test_serie_7_dias_7_items(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [
                    {"Timestamp": f"2026-07-{6+i:02d}T12:00:00-03:00",
                     "Value": {"Value": 100.0}}
                    for i in range(7)
                ]
            },
        }

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="sum",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-13T00:00:00-03:00",
                data_method="summary",
                summary_type="Average",
                summary_duration="1d",
                calculation_basis="TimeWeighted",
                group_by="1d",
                return_series=True,
            )

        assert result["ok"] is True
        assert len(result["tool_result"]["results"]) == 1
        r = result["tool_result"]["results"][0]
        assert len(r["series"]) == 7
        assert r["group_by"] == "1d"
        assert r["total"] is not None
        assert r["unidade_final_inferida"] == "Nm3"

    @pytest.mark.asyncio
    async def test_serie_campos_obrigatorios(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [
                    {"Timestamp": "2026-07-06T12:00:00-03:00",
                     "Value": {"Value": 100.0}}
                ]
            },
        }

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="sum",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                summary_type="Average",
                summary_duration="1d",
                calculation_basis="TimeWeighted",
                group_by="1d",
                return_series=True,
            )

        r = result["tool_result"]["results"][0]
        item = r["series"][0]
        for campo in ("label", "period_start", "period_end", "value", "unit", "quality"):
            assert campo in item, f"Campo '{campo}' ausente no item da série"

    @pytest.mark.asyncio
    async def test_backward_compatibility_sem_group_by(self):
        """Chamada antiga sem group_by nem return_series deve retornar estrutura escalar."""
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [
                    {"Timestamp": "2026-07-06T12:00:00-03:00",
                     "Value": {"Value": 100.0}}
                ]
            },
        }

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ), patch(
            "domain.analytics.clients.math_tool_client.call_stats",
            AsyncMock(return_value={"ok": True, "input_count": 1,
                                     "operations": ["sum"], "result": {"sum": 100.0}}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="sum",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                summary_type="Average",
                summary_duration="1d",
                calculation_basis="TimeWeighted",
            )

        assert result["ok"] is True
        r = result["tool_result"]["results"][0]
        assert "series" not in r, "Modo escalar não deve ter campo 'series'"
        assert "result" in r, "Modo escalar deve ter campo 'result'"

    @pytest.mark.asyncio
    async def test_periodo_sem_dados_cobertura(self):
        """Períodos sem dados não devem sumir do output."""
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        # Mock com apenas 3 dias de dados em 7
        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [
                    {"Timestamp": "2026-07-06T12:00:00-03:00",
                     "Value": {"Value": 100.0}},
                    {"Timestamp": "2026-07-08T12:00:00-03:00",
                     "Value": {"Value": 110.0}},
                    {"Timestamp": "2026-07-10T12:00:00-03:00",
                     "Value": {"Value": 90.0}},
                ]
            },
        }

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value=pi_response),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="sum",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-13T00:00:00-03:00",
                data_method="summary",
                summary_type="Average",
                summary_duration="1d",
                calculation_basis="TimeWeighted",
                group_by="1d",
                return_series=True,
            )

        r = result["tool_result"]["results"][0]
        assert len(r["series"]) == 7, "Deveria ter 7 buckets mesmo com dados parciais"
        nulls = [i for i in r["series"] if i["value"] is None]
        assert len(nulls) == 4, "4 buckets deveriam ser null (sem dados)"

    @pytest.mark.asyncio
    async def test_group_by_invalido_erro_controlado(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="sum",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                group_by="invalid_value",
                return_series=True,
            )

        assert result["ok"] is False
        assert result["answer_generation_error"] is not None
        assert "group_by inválido" in result["output"] or "group_by inválido" in result["answer_generation_error"]


class TestExecutarEstatisticaStatus:
    """Test status codes returned by executar_estatistica_tags_service."""

    @pytest.mark.asyncio
    async def test_group_by_invalido_status(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="sum",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                group_by="invalid_value",
                return_series=True,
            )

        assert result["ok"] is False
        assert result["status"] == "invalid_argument"
        assert result["error_code"] == "INVALID_GROUP_BY"
        assert "group_by inválido" in result["output"]

    @pytest.mark.asyncio
    async def test_data_method_invalido_status(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="xyz_invalido",
            )

        assert result["ok"] is False
        assert result["status"] == "invalid_argument"
        assert result["error_code"] == "INVALID_DATA_METHOD"

    @pytest.mark.asyncio
    async def test_sucesso_status(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )
        from domain.analytics.clients.math_tool_client import call_stats

        pi_response = {
            "point_metadata": {"EngineeringUnits": "Nm3/h"},
            "raw_data": {
                "Items": [
                    {"Value": {"Value": 100.0}, "Timestamp": "2026-07-06T01:00:00-03:00"},
                    {"Value": {"Value": 110.0}, "Timestamp": "2026-07-06T02:00:00-03:00"},
                ]
            },
        }

        with (
            patch(
                "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
                AsyncMock(return_value=pi_response),
            ),
            patch(
                "domain.analytics.services.math_tool_service.call_stats",
                AsyncMock(return_value={"mean": 105.0}),
            ),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="mean",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                summary_type="Average",
            )

        assert result["ok"] is True
        assert result["status"] == "success"
        assert result["error_code"] is None
        assert isinstance(result["output"], str)

    @pytest.mark.asyncio
    async def test_backward_compatibility_output(self):
        from domain.analytics.services.math_tool_service import (
            executar_estatistica_tags_service,
        )

        with patch(
            "domain.analytics.utils.math_pi_series.buscar_dados_temporais_tag",
            AsyncMock(return_value={}),
        ):
            result = await executar_estatistica_tags_service(
                tags=["LFI_RB3_VAZ_GN_TOTAL"],
                operation="sum",
                start_time="2026-07-06T00:00:00-03:00",
                end_time="2026-07-07T00:00:00-03:00",
                data_method="summary",
                group_by="invalid_value",
                return_series=True,
            )

        assert isinstance(result["output"], str)
        assert "answer_generation_error" in result


class TestDocumentacao:
    """Testes de verificação textual da documentação."""

    def test_prompt_nao_proibe_1m(self):
        content = open("app/prompts/agent_prompt.py").read()
        assert "1m não é válido" not in content, (
            "Prompt não deve afirmar que 1m é inválido"
        )

    def test_rag_nao_exclui_1m(self):
        content = open("PI_WEB_API_AGENT_GUIDE.md").read()
        assert "Não utilizar" not in content or "1m" not in content, (
            "RAG não deve afirmar que 1m não deve ser utilizado"
        )

    def test_agents_md_lista_1m(self):
        content = open("AGENTS.md").read()
        assert "1m" in content, (
            "AGENTS.md deve listar 1m como valor válido de group_by"
        )
