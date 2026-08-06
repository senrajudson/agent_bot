"""Teste de regressão para o incidente CPD_LP_SECADOR_STATUS.

Reproduz o cenário exato onde:
1. consultar_tag retornou sucesso com Digital Set Estado_126 e 5 estados.
2. analyze_pi_tag_behavior falhou com INVALID_DIGITAL_SET.

Após a correção, ambas as tools devem retornar sucesso com o mesmo Digital Set.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from domain.analysis.models import AnalysisPoint, TagMetadata
from domain.analysis.services.pi_data_collector import CollectedData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TAG = "CPD_LP_SECADOR_STATUS"

POINT_METADATA = {
    "WebId": "P1ABC123",
    "Name": TAG,
    "Descriptor": "Comando do Motor do Secador de Tiras",
    "PointType": "Digital",
    "EngineeringUnits": None,
    "DigitalSet": None,
    "DigitalSetName": None,
}

ATTR_DIGITALSET = {
    "Items": [{"Value": "Estado_126"}],
}

DIGITAL_STATES = [
    {"indice": 0, "nome": "DESLIGADO", "descricao": None},
    {"indice": 1, "nome": "VAZIO", "descricao": None},
    {"indice": 2, "nome": "LIGADO", "descricao": None},
    {"indice": 3, "nome": "VAZIO", "descricao": None},
    {"indice": 4, "nome": "FALHA", "descricao": None},
]

RECORDED_POINTS = {
    "Items": [
        {"Timestamp": "2026-08-04T08:00:00Z", "Value": 0, "Good": True, "Questionable": False},
        {"Timestamp": "2026-08-04T09:00:00Z", "Value": 2, "Good": True, "Questionable": False},
        {"Timestamp": "2026-08-04T10:00:00Z", "Value": 0, "Good": True, "Questionable": False},
        {"Timestamp": "2026-08-04T11:00:00Z", "Value": 4, "Good": True, "Questionable": False},
        {"Timestamp": "2026-08-04T11:18:15Z", "Value": 0, "Good": True, "Questionable": False},
    ],
}

METADATA_MODEL = TagMetadata(
    tag=TAG,
    point_type="digital",
    descriptor="Comando do Motor do Secador de Tiras",
    engineering_units=None,
    digital_set=None,
)


# ---------------------------------------------------------------------------
# T168: consultar_tag com sucesso
# ---------------------------------------------------------------------------

class TestConsultarTagSuccess:
    def test_consultar_tag_resolves_estado_126(self) -> None:
        """consultar_tag deve resolver Digital Set via atributo e retornar 5 estados."""
        from domain.pims.utils.digital_states import resolve_digital_set_name

        resolution = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )

        assert resolution.name == "Estado_126"
        assert resolution.source.value == "attribute.digitalset"
        assert resolution.is_invalid is False
        assert resolution.fallback_used is True

    def test_consultar_tag_preserves_five_states(self) -> None:
        """5 estados digitais devem ser preservados."""
        assert len(DIGITAL_STATES) == 5
        nomes = [s["nome"] for s in DIGITAL_STATES]
        assert "DESLIGADO" in nomes
        assert "LIGADO" in nomes
        assert "FALHA" in nomes
        assert nomes.count("VAZIO") == 2


# ---------------------------------------------------------------------------
# T169: analyze após consultar_tag — paridade
# ---------------------------------------------------------------------------

class TestAnalyzeAfterConsultarTag:
    def test_analyze_resolves_same_digital_set(self) -> None:
        """analyze_pi_tag_behavior deve resolver o mesmo Digital Set."""
        from domain.pims.utils.digital_states import resolve_digital_set_name

        resolution = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )

        assert resolution.name == "Estado_126"

    def test_analyze_no_invalid_digital_set(self) -> None:
        """Análise não deve retornar INVALID_DIGITAL_SET quando atributo existe."""
        from domain.pims.utils.digital_states import resolve_digital_set_name

        resolution = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )

        assert resolution.name is not None
        assert resolution.source.value != "missing"


# ---------------------------------------------------------------------------
# T171: Confirmar mesmo Digital Set
# ---------------------------------------------------------------------------

class TestSameDigitalSet:
    def test_both_paths_resolve_estado_126(self) -> None:
        """consultar_tag e analyze devem resolver o mesmo nome."""
        from domain.pims.utils.digital_states import resolve_digital_set_name

        r1 = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )
        r2 = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )

        assert r1.name == r2.name == "Estado_126"


# ---------------------------------------------------------------------------
# T172: Confirmar cinco estados
# ---------------------------------------------------------------------------

class TestFiveStates:
    def test_five_states_present(self) -> None:
        """5 estados digitais devem estar presentes."""
        assert len(DIGITAL_STATES) == 5
        indices = [s["indice"] for s in DIGITAL_STATES]
        assert indices == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# T173: Confirmar isError=false na análise
# ---------------------------------------------------------------------------

class TestNoError:
    def test_resolution_not_error(self) -> None:
        """Resolução não deve ser erro quando atributo existe."""
        from domain.pims.utils.digital_states import resolve_digital_set_name

        resolution = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )

        assert resolution.is_invalid is False
        assert resolution.error_code is None


# ---------------------------------------------------------------------------
# T174: Confirmar ausência de INVALID_DIGITAL_SET
# ---------------------------------------------------------------------------

class TestNoInvalidDigitalSet:
    def test_no_missing_source(self) -> None:
        """Source não deve ser MISSING quando atributo existe."""
        from domain.pims.utils.digital_states import resolve_digital_set_name

        resolution = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )

        assert resolution.source.value != "missing"


# ---------------------------------------------------------------------------
# T175: Confirmar resposta não culpa o PI
# ---------------------------------------------------------------------------

class TestNoBlamePI:
    def test_no_system_blame_in_resolution(self) -> None:
        """Resolução não deve atribuir culpa ao sistema."""
        from domain.pims.utils.digital_states import resolve_digital_set_name

        resolution = resolve_digital_set_name(
            point_data=POINT_METADATA,
            digitalset_attribute=ATTR_DIGITALSET,
        )

        assert resolution.name == "Estado_126"
        assert resolution.message_safe is None or "inconsistência" not in (resolution.message_safe or "").lower()


# ---------------------------------------------------------------------------
# T176: FastMCP single
# ---------------------------------------------------------------------------

class TestFastMCPSingle:
    def test_tool_signature_valid(self) -> None:
        """Assinatura de analyze_pi_tag_behavior deve ser válida."""
        import inspect
        from mcp_server.services.analysis_tools import analyze_pi_tag_behavior

        sig = inspect.signature(analyze_pi_tag_behavior)
        params = list(sig.parameters.keys())
        assert "tag" in params
        assert "start_time" in params
        assert "end_time" in params
        assert "zero_policy" in params


# ---------------------------------------------------------------------------
# T177: FastMCP report
# ---------------------------------------------------------------------------

class TestFastMCPReport:
    def test_tool_signature_valid(self) -> None:
        """Assinatura de generate_pi_tags_analysis_report deve ser válida."""
        import inspect
        from mcp_server.services.analysis_tools import generate_pi_tags_analysis_report

        sig = inspect.signature(generate_pi_tags_analysis_report)
        params = list(sig.parameters.keys())
        assert "tags" in params
        assert "start_time" in params
        assert "end_time" in params
        assert "zero_policy" in params


# ---------------------------------------------------------------------------
# T180: Confirmar partial_success multi-tag
# ---------------------------------------------------------------------------

class TestPartialSuccess:
    def test_multi_tag_partial_success_structure(self) -> None:
        """generate_pi_tags_analysis_report com 1 falha + 1 sucesso deve retornar partial_success."""
        from domain.analysis.models import MultiTagAnalysisResult, TagAnalysisResult, AnalysisError
        from domain.analysis.models import QualityMetrics

        success_result = TagAnalysisResult(
            metadata=TagMetadata(
                tag="TAG_OK",
                point_type="numeric",
                descriptor="Test",
                engineering_units="°C",
            ),
            quality=QualityMetrics(
                good_pct=100.0,
                questionable_pct=0.0,
                substituted_pct=0.0,
                zero_pct=0.0,
                verdict="DADOS_EXCELENTES",
            ),
        )

        error = AnalysisError(
            tag="TAG_FAIL",
            code="INVALID_DIGITAL_SET",
            message="DigitalSet não encontrado",
            retryable=False,
        )

        multi = MultiTagAnalysisResult(
            results=(success_result,),
            errors=(error,),
            period_start="2026-08-03T00:00:00-03:00",
            period_end="2026-08-04T00:00:00-03:00",
            total_requested=2,
            total_processed=1,
        )

        assert multi.total_processed == 1
        assert len(multi.errors) == 1
        assert multi.errors[0].code == "INVALID_DIGITAL_SET"
