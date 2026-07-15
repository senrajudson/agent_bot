"""Validate that services return interpretable outputs with quality glosa, veredict, etc."""

from __future__ import annotations

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


# ── status_pims: veredict ──


class TestStatusPimsVeredito:
    def test_excelente_sem_falhas_com_informativos(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_veredito,
        )

        v = _build_veredito(
            {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 10, "total_logs": 10},
            "CONECTADO",
        )
        assert v == "EXCELENTE"

    def test_alerta_warnings_acima_limite_absoluto(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_veredito,
        )

        v = _build_veredito(
            {"erros_criticos": 0, "alertas_reais": 60, "client_aborted": 0,
             "informativos": 4940, "total_logs": 5000},
            "CONECTADO",
        )
        assert v == "ALERTA"

    def test_critico_with_errors(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_veredito,
        )

        v = _build_veredito(
            {"erros_criticos": 1, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 9, "total_logs": 10},
            "CONECTADO",
        )
        assert v == "CRÍTICO"

    def test_saudavel_zero_logs(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_veredito,
        )

        v = _build_veredito(
            {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 0, "total_logs": 0},
            "CONECTADO",
        )
        assert v == "SAUDÁVEL"

    def test_output_starts_with_veredito(self):
        from domain.pims_ops.services.status_pims_service import _build_status_output

        summary = {"total_logs": 5, "total_errors": 1, "total_warnings": 0,
                    "erros_criticos": 1, "alertas_reais": 0, "informativos": 4,
                    "client_aborted": 0, "ignorados_benignos": 0,
                    "recent_errors": [], "recent_warnings": [],
                    "recent_critical": [], "recent_real_alerts": [],
                    "recent_client_aborted": [], "recent_logs": []}
        output = _build_status_output(summary, "CONECTADO")
        assert output.startswith("Status do PIMS:")

    def test_output_excelente_veredito(self):
        from domain.pims_ops.services.status_pims_service import _build_status_output
        from domain.pims_ops.services.status_pims_service import _MENSAGENS_POR_NIVEL

        summary = {"total_logs": 10, "total_errors": 0, "total_warnings": 0,
                    "erros_criticos": 0, "alertas_reais": 0, "informativos": 10,
                    "client_aborted": 0, "ignorados_benignos": 0,
                    "recent_errors": [], "recent_warnings": [],
                    "recent_critical": [], "recent_real_alerts": [],
                    "recent_client_aborted": [], "recent_logs": []}
        output = _build_status_output(summary, "CONECTADO")
        assert "Status do PIMS: EXCELENTE" in output
        assert _MENSAGENS_POR_NIVEL["EXCELENTE"] in output


# ── status_pims: classify_line (Tarefa 7) ──


class TestClassifyLine:
    """Pure unit tests for _classify_line — 5 categories."""

    def test_http_200_informativo(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('GET /piwebapi HTTP/1.1" 200') == "informativo"

    def test_http_201_informativo(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 201 Created') == "informativo"

    def test_http_204_informativo(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 204 No Content') == "informativo"

    def test_http_304_informativo(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 304 Not Modified') == "informativo"

    def test_http_200_with_slow_ignorado_benigno(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('GET /piwebapi HTTP/1.1" 200 slow') == "ignorado_benigno"

    def test_http_200_with_warning_ignorado_benigno(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('GET /piwebapi HTTP/1.1" 200 warning') == "ignorado_benigno"

    def test_http_200_with_retry_ignorado_benigno(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('GET /piwebapi HTTP/1.1" 200 retry') == "ignorado_benigno"

    def test_http_400_alerta_real(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 400 Bad Request') == "alerta_real"

    def test_http_401_alerta_real(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 401 Unauthorized') == "alerta_real"

    def test_http_404_alerta_real(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 404 Not Found') == "alerta_real"

    def test_http_429_alerta_real(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 429 Too Many Requests') == "alerta_real"

    def test_http_500_erro_critico(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 500 Internal Error') == "erro_critico"

    def test_http_503_erro_critico(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 503 Unavailable') == "erro_critico"

    def test_sem_http_critical_keyword_erro_critico(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('exception in worker thread') == "erro_critico"

    def test_sem_http_alert_keyword_alerta_real(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('warning: deprecated endpoint') == "alerta_real"

    def test_sem_http_info_pattern_informativo(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('service started') == "informativo"

    def test_sem_http_default_ignorado_benigno(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('random log line') == "ignorado_benigno"

    def test_porta_nao_vira_http(self):
        from domain.pims_ops.services.status_pims_service import (
            _extract_http_status,
        )
        assert _extract_http_status('10.247.140.96:443') is None

    def test_timestamp_nao_vira_http(self):
        from domain.pims_ops.services.status_pims_service import (
            _extract_http_status,
        )
        assert _extract_http_status('14/Jul/2026') is None

    def test_multiplos_http_ultimo_usado(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('301 -> 200 OK') == "informativo"

    def test_http_code_no_false_positive(self):
        from domain.pims_ops.services.status_pims_service import (
            _extract_http_status,
        )
        assert _extract_http_status('version 1.234.5') is None

    # ── client_aborted (nova categoria, 5ª) ──

    def test_http_499_client_aborted(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 499') == "client_aborted"

    def test_http_499_post_batch_client_aborted(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('POST /piwebapi/batch HTTP/1.1" 499') == "client_aborted"

    def test_http_499_com_texto_client_aborted(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 499 Client Closed Request') == "client_aborted"

    def test_http_4xx_outros_alerta_real(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 400') == "alerta_real"

    def test_http_5xx_continua_erro_critico(self):
        from domain.pims_ops.services.status_pims_service import _classify_line
        assert _classify_line('HTTP/1.1" 503') == "erro_critico"


# ── status_pims: veredito v3 (11 regras, 6 níveis) ──


class TestStatusPimsVereditoV3:
    """Nova precedência com 11 regras e 6 níveis."""

    # ── EXCELENTE (regra 10) ──

    def test_excelente_cenario_enunciado(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 5000, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "EXCELENTE"

    # ── ALERTA (regras 4, 5, 6, 7) ──

    def test_alerta_limite_absoluto(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 60, "client_aborted": 0,
             "informativos": 4940, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "ALERTA"

    def test_alerta_limite_percentual(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 5, "client_aborted": 0,
             "informativos": 95, "total_logs": 100}
        v = _build_veredito(s, "CONECTADO")
        assert v == "ALERTA"

    def test_alerta_client_aborted_acima_limite_absoluto(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 1500,
             "informativos": 3500, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "ALERTA"

    def test_alerta_client_aborted_acima_limite_percentual(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 2000,
             "informativos": 3000, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "ALERTA"

    def test_alerta_dataserver_desconectado_sem_erro(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 100, "total_logs": 100}
        v = _build_veredito(s, "DESCONECTADO")
        assert v == "ALERTA"

    def test_alerta_dataserver_inconfiavel(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 100, "total_logs": 100}
        v = _build_veredito(s, "INCONFIÁVEL")
        assert v == "ALERTA"

    def test_alerta_dataserver_indisponivel_com_logs(self):
        """R4=B: DS INDISPONÍVEL com logs sem falhas → ALERTA."""
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 100, "total_logs": 100}
        v = _build_veredito(s, "INDISPONÍVEL")
        assert v == "ALERTA"

    # ── CRÍTICO (regras 2, 3) ──

    def test_critico_com_erro(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 1, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 99, "total_logs": 100}
        v = _build_veredito(s, "CONECTADO")
        assert v == "CRÍTICO"

    def test_critico_dataserver_desconectado_com_erro(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 1, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 99, "total_logs": 100}
        v = _build_veredito(s, "DESCONECTADO")
        assert v == "CRÍTICO"

    # ── OPERACIONAL (regra 8) ──

    def test_operacional_client_aborted_233(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 233,
             "informativos": 4767, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "OPERACIONAL"

    def test_operacional_client_aborted_abaixo_limite_absoluto_e_percentual(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 2, "client_aborted": 100,
             "informativos": 4898, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "OPERACIONAL"

    # ── SAUDÁVEL (regras 9, 11) ──

    def test_saudavel_zero_logs_dataserver_conectado(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 0, "total_logs": 0}
        v = _build_veredito(s, "CONECTADO")
        assert v == "SAUDÁVEL"

    def test_saudavel_fallback_sem_informativos(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 0, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "SAUDÁVEL"

    # ── OFFLINE (regra 1) ──

    def test_offline_dataserver_indisponivel_zero_logs(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 0, "client_aborted": 0,
             "informativos": 0, "total_logs": 0}
        v = _build_veredito(s, "INDISPONÍVEL")
        assert v == "OFFLINE"

    # ── EXCELENTE com informativos (regra 10) ──

    def test_saudavel_abaixo_limite_absoluto(self):
        """40 alertas é abaixo do limite absoluto (50). Sem client_aborted, fallback → SAUDÁVEL."""
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 40, "client_aborted": 0,
             "informativos": 4960, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "SAUDÁVEL"

    def test_saudavel_abaixo_limite_percentual(self):
        """2 alertas em 5000 (0.04%) é abaixo do limite percentual (1%). Sem client_aborted, fallback → SAUDÁVEL."""
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 0, "alertas_reais": 2, "client_aborted": 0,
             "informativos": 4998, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "SAUDÁVEL"

    # ── Precedência: erro sobrepõe OPERACIONAL ──

    def test_critico_erro_predomina_sobre_operacional(self):
        from domain.pims_ops.services.status_pims_service import _build_veredito
        s = {"erros_criticos": 1, "alertas_reais": 0, "client_aborted": 233,
             "informativos": 4766, "total_logs": 5000}
        v = _build_veredito(s, "CONECTADO")
        assert v == "CRÍTICO"


# ── status_pims: dataserver check helpers + service integration ──


class TestDataServerHelpers:
    """Pure unit tests for dataserver helpers (B1-B5)."""

    # B1: _normalize_dataserver_response

    def test_normalize_with_items(self):
        from domain.pims_ops.services.status_pims_service import (
            _normalize_dataserver_response,
        )

        raw = {"endpoint": "http://test/api/dataservers", "items": [{"Name": "pims"}], "error": None}
        result = _normalize_dataserver_response(raw)
        assert result["endpoint"] == "http://test/api/dataservers"
        assert result["items_count"] == 1
        assert result["error"] is None

    def test_normalize_empty_items(self):
        from domain.pims_ops.services.status_pims_service import (
            _normalize_dataserver_response,
        )

        result = _normalize_dataserver_response({"items": []})
        assert result["items_count"] == 0

    def test_normalize_missing_items_key(self):
        from domain.pims_ops.services.status_pims_service import (
            _normalize_dataserver_response,
        )

        result = _normalize_dataserver_response({})
        assert result["items_count"] == 0

    def test_normalize_with_error(self):
        from domain.pims_ops.services.status_pims_service import (
            _normalize_dataserver_response,
        )

        raw = {"endpoint": "http://test/api/dataservers", "error": "HTTP 500"}
        result = _normalize_dataserver_response(raw)
        assert result["error"] == "HTTP 500"

    # B2: _select_expected_dataserver

    def test_select_exact_match(self):
        from domain.pims_ops.services.status_pims_service import (
            _select_expected_dataserver,
        )

        items = [{"Name": "pims"}, {"Name": "other"}]
        found, item, names = _select_expected_dataserver(items, "pims")
        assert found is True
        assert item["Name"] == "pims"

    def test_select_case_insensitive(self):
        from domain.pims_ops.services.status_pims_service import (
            _select_expected_dataserver,
        )

        items = [{"Name": "PIMS"}, {"Name": "other"}]
        found, item, names = _select_expected_dataserver(items, "pims")
        assert found is True
        assert item["Name"] == "PIMS"

    def test_select_no_match(self):
        from domain.pims_ops.services.status_pims_service import (
            _select_expected_dataserver,
        )

        items = [{"Name": "server_a"}, {"Name": "server_b"}]
        found, item, names = _select_expected_dataserver(items, "pims")
        assert found is False
        assert item is None
        assert "server_a" in names

    def test_select_single_item_no_name(self):
        from domain.pims_ops.services.status_pims_service import (
            _select_expected_dataserver,
        )

        items = [{"Id": "abc123"}]
        found, item, names = _select_expected_dataserver(items, "pims")
        assert found is True
        assert item["Id"] == "abc123"

    def test_select_empty_items(self):
        from domain.pims_ops.services.status_pims_service import (
            _select_expected_dataserver,
        )

        found, item, names = _select_expected_dataserver([], "pims")
        assert found is False
        assert item is None
        assert names == []

    # B3: _build_dataserver_veredito

    def test_veredito_conectado(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_veredito,
        )

        v = _build_dataserver_veredito(matched=True, is_connected=True, has_required_fields=True, error=None)
        assert v == "CONECTADO"

    def test_veredito_desconectado(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_veredito,
        )

        v = _build_dataserver_veredito(matched=True, is_connected=False, has_required_fields=True, error=None)
        assert v == "DESCONECTADO"

    def test_veredito_inconfiavel(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_veredito,
        )

        v = _build_dataserver_veredito(matched=True, is_connected=None, has_required_fields=True, error=None)
        assert v == "INCONFIÁVEL"

    def test_veredito_inconfiavel_sem_campos(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_veredito,
        )

        v = _build_dataserver_veredito(matched=True, is_connected=True, has_required_fields=False, error=None)
        assert v == "INCONFIÁVEL"

    def test_veredito_ausente(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_veredito,
        )

        v = _build_dataserver_veredito(matched=False, is_connected=None, has_required_fields=False, error=None)
        assert v == "AUSENTE"

    def test_veredito_indisponivel(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_veredito,
        )

        v = _build_dataserver_veredito(matched=False, is_connected=None, has_required_fields=False, error="HTTP 500")
        assert v == "INDISPONÍVEL"

    # B5: _build_overall_status

    def test_overall_status_excelente_conectado(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("EXCELENTE", "CONECTADO")
        assert s == "excellent"

    def test_overall_status_saudavel_conectado(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("SAUDÁVEL", "CONECTADO")
        assert s == "healthy"

    def test_overall_status_operacional_conectado(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("OPERACIONAL", "CONECTADO")
        assert s == "operational"

    def test_overall_status_operacional_dataserver_desconectado(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("OPERACIONAL", "DESCONECTADO")
        assert s == "warning"

    def test_overall_status_critical(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("CRÍTICO", "CONECTADO")
        assert s == "critical"

    def test_overall_status_offline(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("OFFLINE", "CONECTADO")
        assert s == "offline"

    def test_overall_status_excelente_inconfiavel(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("EXCELENTE", "INCONFIÁVEL")
        assert s == "warning"

    def test_overall_status_offline_indisponivel(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("OFFLINE", "INDISPONÍVEL")
        assert s == "offline"

    def test_overall_status_legado_normal(self):
        """Defensive fallback: NORMAL aceito como entrada."""
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("NORMAL", "CONECTADO")
        assert s == "healthy"

    def test_overall_status_legado_ok(self):
        """Defensive fallback: OK aceito como entrada."""
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("OK", "CONECTADO")
        assert s == "healthy"

    def test_overall_status_legado_indeterminado(self):
        """Defensive fallback: INDETERMINADO aceito como entrada."""
        from domain.pims_ops.services.status_pims_service import (
            _build_overall_status,
        )

        s = _build_overall_status("INDETERMINADO", "AUSENTE")
        assert s == "indeterminate"


class TestDataServerOutput:
    """Test B4: _build_dataserver_output formatting."""

    def test_output_contains_veredito_conectado(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_output,
        )

        info = {
            "matched": True,
            "name": "pims",
            "web_id": "F1DS...",
            "is_connected": True,
            "server_version": "3.4.425.1435",
            "server_time": "2026-07-08T17:04:46Z",
            "path": None,
        }
        output = _build_dataserver_output("http://test/dataservers", "CONECTADO", info, None)
        assert "PI Web API / DataServer" in output
        assert "Veredito: CONECTADO" in output
        assert "IsConnected: True" in output
        assert "ServerVersion: 3.4.425.1435" in output
        assert "Password" not in output
        assert "Authorization" not in output

    def test_output_with_error(self):
        from domain.pims_ops.services.status_pims_service import (
            _build_dataserver_output,
        )

        info = {"matched": False, "name": None}
        output = _build_dataserver_output("http://test/dataservers", "INDISPONÍVEL", info, "HTTP 500")
        assert "Veredito: INDISPONÍVEL" in output
        assert "Erro: HTTP 500" in output


class TestDataServerServiceEndToEnd:
    """Service-level tests with mocked external calls.
    Imports are now lazy (inside functions), so patch at definition source.
    """

    @pytest.mark.asyncio
    async def test_service_logs_ok_dataserver_ok(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        loki_mock = {"data": {"result": [{"values": [["1", "healthy daemon running"]]}]}}
        ds_mock = {
            "endpoint": "http://test/dataservers",
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
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(return_value=loki_mock),
        ), patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_status_pims_service()

        assert result["ok"] is True
        assert "Status do PIMS: EXCELENTE" in result["output"]
        assert "PI Web API / DataServer" in result["output"]
        assert "Veredito: CONECTADO" in result["output"]
        assert result["tool_result"]["dataserver_check"]["veredito"] == "CONECTADO"
        assert result["tool_result"]["dataserver_check"]["ok"] is True
        assert result["tool_result"]["status"] == "EXCELENTE"
        assert result["tool_result"]["overall_status"] == "excellent"

    @pytest.mark.asyncio
    async def test_service_logs_ok_dataserver_falha_isolada(self):
        """R4=B: DS INDISPONÍVEL + logs OK → ALERTA."""
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        loki_mock = {"data": {"result": [{"values": [["1", "healthy daemon running"]]}]}}

        with patch(
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(return_value=loki_mock),
        ), patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(side_effect=Exception("Connection timeout")),
        ):
            result = await consultar_status_pims_service()

        assert result["ok"] is True, "ok deve ser True mesmo com falha isolada do DataServer"
        assert "PI Web API / DataServer" in result["output"], "Seção do DataServer deve aparecer"
        assert "Veredito: INDISPONÍVEL" in result["output"]
        assert result["tool_result"]["status"] == "ALERTA", "R4=B: DS INDISPONÍVEL + logs OK → ALERTA"
        assert result["tool_result"]["dataserver_check"]["veredito"] == "INDISPONÍVEL"
        assert result["tool_result"]["dataserver_check"]["ok"] is False
        assert result["tool_result"]["overall_status"] == "warning"

    @pytest.mark.asyncio
    async def test_service_logs_falham_retorno_precoce(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        with patch(
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(side_effect=Exception("Loki down")),
        ):
            result = await consultar_status_pims_service()

        assert result["ok"] is False
        assert "Loki down" in result["output"]
        assert "dataserver_check" not in result.get("tool_result", {})

    @pytest.mark.asyncio
    async def test_service_logs_ok_dataserver_desconectado(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        loki_mock = {"data": {"result": [{"values": [["1", "healthy daemon running"]]}]}}
        ds_mock = {
            "endpoint": "http://test/dataservers",
            "items": [{
                "Name": "pims",
                "WebId": "F1DS...",
                "IsConnected": False,
                "ServerVersion": "3.4.425.1435",
                "ServerTime": "2026-07-08T17:04:46Z",
                "Path": "\\\\PIServers[pims]",
            }],
            "error": None,
        }

        with patch(
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(return_value=loki_mock),
        ), patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_status_pims_service()

        assert result["ok"] is True
        assert "Veredito: DESCONECTADO" in result["output"]
        assert result["tool_result"]["status"] == "ALERTA"
        assert result["tool_result"]["dataserver_check"]["veredito"] == "DESCONECTADO"
        assert result["tool_result"]["overall_status"] == "warning"

    @pytest.mark.asyncio
    async def test_nenhuma_credencial_vazada_no_output(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        loki_mock = {"data": {"result": [{"values": [["1", "healthy daemon running"]]}]}}
        ds_mock = {
            "endpoint": "http://test/dataservers",
            "items": [{"Name": "pims", "WebId": "F1DS...", "IsConnected": True}],
            "error": None,
        }

        with patch(
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(return_value=loki_mock),
        ), patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_status_pims_service()

        output = result["output"]
        assert "password" not in output.lower()
        assert "secret" not in output.lower()
        assert "token" not in output.lower()
        assert "Authorization" not in output

    @pytest.mark.asyncio
    async def test_service_logs_ok_dataserver_items_vazio(self):
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        loki_mock = {"data": {"result": [{"values": [["1", "healthy daemon running"]]}]}}
        ds_mock = {
            "endpoint": "http://test/dataservers",
            "items": [],
            "error": None,
        }

        with patch(
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(return_value=loki_mock),
        ), patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_status_pims_service()

        assert result["ok"] is True
        assert result["tool_result"]["status"] == "ALERTA"
        assert result["tool_result"]["dataserver_check"]["veredito"] == "AUSENTE"
        assert result["tool_result"]["overall_status"] == "warning"
        assert "Veredito: AUSENTE" in result["output"]

    @pytest.mark.asyncio
    async def test_service_cenario_enunciado_http_200(self):
        """Cenário do enunciado: 5000 logs, 8 HTTP 200 com 'slow', DataServer CONECTADO → EXCELENTE."""
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        loki_lines = (
            ['GET /piwebapi/points?... HTTP/1.1" 200 1234 0.005'] * 4992
            + ['GET /piwebapi/points?... HTTP/1.1" 200 1234 5.2s slow'] * 8
        )
        loki_mock = {
            "data": {
                "result": [
                    {"values": [[str(i), line] for i, line in enumerate(loki_lines)]}
                ]
            }
        }
        ds_mock = {
            "endpoint": "http://test/dataservers",
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
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(return_value=loki_mock),
        ), patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_status_pims_service()

        assert result["ok"] is True
        assert result["tool_result"]["status"] == "EXCELENTE"
        assert result["tool_result"]["overall_status"] == "excellent"
        assert result["tool_result"]["summary"]["alertas_reais"] == 0
        assert result["tool_result"]["summary"]["ignorados_benignos"] == 8
        assert result["tool_result"]["summary"]["erros_criticos"] == 0
        assert result["tool_result"]["summary"]["informativos"] == 4992
        assert result["tool_result"]["summary"]["total_errors"] == 0
        assert result["tool_result"]["summary"]["total_warnings"] == 0
        assert "Status do PIMS: EXCELENTE" in result["output"]
        assert "benignos" in result["output"]
        assert result["tool_result"]["dataserver_check"]["veredito"] == "CONECTADO"
        assert "PI Web API / DataServer" in result["output"]

    @pytest.mark.asyncio
    async def test_service_cenario_enunciado_http_499(self):
        """Cenário do enunciado: 5000 logs, 233 HTTP 499, DataServer CONECTADO → OPERACIONAL."""
        from domain.pims_ops.services.status_pims_service import (
            consultar_status_pims_service,
        )

        loki_lines = (
            ['GET /piwebapi/points?... HTTP/1.1" 200 1234 0.005'] * 4767
            + ['POST /piwebapi/batch HTTP/1.1" 499'] * 233
        )
        loki_mock = {
            "data": {
                "result": [
                    {"values": [[str(i), line] for i, line in enumerate(loki_lines)]}
                ]
            }
        }
        ds_mock = {
            "endpoint": "http://test/dataservers",
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
            "domain.pims_ops.clients.grafana_loki_client.query_loki_range",
            AsyncMock(return_value=loki_mock),
        ), patch(
            "domain.pims.clients.pi_web_api_client.get_dataservers",
            AsyncMock(return_value=ds_mock),
        ):
            result = await consultar_status_pims_service()

        assert result["ok"] is True
        assert result["tool_result"]["status"] == "OPERACIONAL"
        assert result["tool_result"]["overall_status"] == "operational"
        assert result["tool_result"]["summary"]["client_aborted"] == 233
        assert result["tool_result"]["summary"]["alertas_reais"] == 0
        assert result["tool_result"]["summary"]["total_warnings"] == 0
        assert "Status do PIMS: OPERACIONAL" in result["output"]
        assert "O ambiente está operacional" in result["output"]
        assert result["tool_result"]["dataserver_check"]["veredito"] == "CONECTADO"


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

    def test_normalizar_group_by_invalido(self):
        from domain.analytics.services.math_tool_service import _normalizar_group_by

        with pytest.raises(ValueError, match="group_by inválido"):
            _normalizar_group_by("xyz")
        with pytest.raises(ValueError, match="group_by inválido"):
            _normalizar_group_by("2d")

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

        buckets = _group_points_by_period(
            points, group_by="1d",
            start_time="2026-07-06T00:00:00-03:00",
            end_time="2026-07-13T00:00:00-03:00",
        )

        assert len(buckets) == 7
        assert all(b["duration_seconds"] == 86400.0 for b in buckets)

    def test_buckets_vazios_incluidos(self):
        from domain.analytics.services.math_tool_service import _group_points_by_period

        # Only 3 points for 7 days
        points = [
            {"timestamp": "2026-07-06T12:00:00-03:00", "value": 100.0},
            {"timestamp": "2026-07-08T12:00:00-03:00", "value": 110.0},
            {"timestamp": "2026-07-10T12:00:00-03:00", "value": 90.0},
        ]

        buckets = _group_points_by_period(
            points, group_by="1d",
            start_time="2026-07-06T00:00:00-03:00",
            end_time="2026-07-13T00:00:00-03:00",
        )

        assert len(buckets) == 7
        empty_buckets = [b for b in buckets if not b["points"]]
        assert len(empty_buckets) == 4  # 7 - 3 with data


class TestCalcularConsumoPorPeriodo:
    """Test _calcular_consumo_por_periodo end-to-end."""

    def test_consumo_nm3_h_sum(self):
        from domain.analytics.services.math_tool_service import (
            _calcular_consumo_por_periodo,
            _group_points_by_period,
        )

        # 1 day, 1 point with avg=100 Nm3/h, bucket=86400s
        points = [{"timestamp": "2026-07-06T12:00:00-03:00", "value": 100.0}]
        buckets = _group_points_by_period(
            points, group_by="1d",
            start_time="2026-07-06T00:00:00-03:00",
            end_time="2026-07-07T00:00:00-03:00",
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

        # Empty points
        buckets = _group_points_by_period(
            [], group_by="1d",
            start_time="2026-07-06T00:00:00-03:00",
            end_time="2026-07-07T00:00:00-03:00",
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

        points = [
            {"timestamp": "2026-07-06T06:00:00-03:00", "value": 90.0},
            {"timestamp": "2026-07-06T12:00:00-03:00", "value": 110.0},
        ]
        buckets = _group_points_by_period(
            points, group_by="1d",
            start_time="2026-07-06T00:00:00-03:00",
            end_time="2026-07-07T00:00:00-03:00",
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

        # Tag without flow unit (e.g. temperature)
        points = [
            {"timestamp": "2026-07-06T06:00:00-03:00", "value": 30.0},
            {"timestamp": "2026-07-06T12:00:00-03:00", "value": 50.0},
        ]
        buckets = _group_points_by_period(
            points, group_by="1d",
            start_time="2026-07-06T00:00:00-03:00",
            end_time="2026-07-07T00:00:00-03:00",
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
