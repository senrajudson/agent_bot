from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from domain.pims.services.tag_attributes_service import (
    _ALIASES,
    _GROUP_ATTRIBUTES,
    _VALID_GROUPS,
    _filter_by_names,
    _format_output,
    _interpret_value,
    _items_to_dict,
    _resolve_group,
    _validar_tag,
    get_tag_attributes,
)

_MOCK_ITEMS = [
    {"Name": "compressing", "Value": 1, "Links": {}},
    {"Name": "CompDev", "Value": 0.05, "Links": {}},
    {"Name": "compdevpercent", "Value": 10, "Links": {}},
    {"Name": "compmin", "Value": 0, "Links": {}},
    {"Name": "compmax", "Value": 300, "Links": {}},
    {"Name": "excdev", "Value": 0.1, "Links": {}},
    {"Name": "excdevpercent", "Value": 5, "Links": {}},
    {"Name": "excmin", "Value": -10, "Links": {}},
    {"Name": "excmax", "Value": 350, "Links": {}},
    {"Name": "scan", "Value": 1, "Links": {}},
    {"Name": "pointsource", "Value": "PIMS", "Links": {}},
    {"Name": "instrumenttag", "Value": "FT-101", "Links": {}},
    {"Name": "engunits", "Value": "Nm3/h", "Links": {}},
    {"Name": "descriptor", "Value": "VAZÃO GN", "Links": {}},
    {"Name": "pointtype", "Value": "Float32", "Links": {}},
    {"Name": "tag", "Value": "LFI_RB3_VAZ_GN_TOTAL", "Links": {}},
    {"Name": "digitalset", "Value": "", "Links": {}},
]


# ---------------------------------------------------------------------------
# _validar_tag
# ---------------------------------------------------------------------------
class TestValidarTag:
    def test_tag_vazia(self):
        with pytest.raises(ValueError, match="Tag vazia ou inválida"):
            _validar_tag("")

    def test_tag_none(self):
        with pytest.raises(ValueError, match="Tag vazia ou inválida"):
            _validar_tag(None)

    def test_tag_ok(self):
        assert _validar_tag(" LFI_RB3_VAZ ") == "LFI_RB3_VAZ"


# ---------------------------------------------------------------------------
# _resolve_group
# ---------------------------------------------------------------------------
class TestResolveGroup:
    def test_grupos_validos(self):
        for g in _VALID_GROUPS:
            assert _resolve_group(g) == g

    def test_alias_metadata(self):
        assert _resolve_group("metadata") == "identity"

    def test_alias_excecao(self):
        assert _resolve_group("exceção") == "exception"

    def test_alias_excessao(self):
        assert _resolve_group("excesso") == "exception"

    def test_alias_exececao(self):
        assert _resolve_group("execeção") == "exception"

    def test_alias_compressao(self):
        assert _resolve_group("compressão") == "compression"

    def test_alias_seguranca(self):
        assert _resolve_group("segurança") == "security"

    def test_grupo_invalido(self):
        with pytest.raises(ValueError, match="Grupo 'xyz123' inválido"):
            _resolve_group("xyz123")

    def test_grupo_vazio(self):
        with pytest.raises(ValueError, match="Grupo não informado"):
            _resolve_group("")


# ---------------------------------------------------------------------------
# _items_to_dict
# ---------------------------------------------------------------------------
class TestItemsToDict:
    def test_lowercase_keys(self):
        result = _items_to_dict([{"Name": "CompDev", "Value": 0.05}])
        assert result == {"compdev": 0.05}

    def test_links_removed(self):
        result = _items_to_dict([{"Name": "Links", "Value": "http://x"}])
        assert "links" not in result

    def test_empty_items(self):
        assert _items_to_dict([]) == {}


# ---------------------------------------------------------------------------
# _filter_by_names
# ---------------------------------------------------------------------------
class TestFilterByName:
    def test_basic_filter(self):
        d = {"compdev": 0.05, "excdev": 0.1, "scan": 1}
        found, missing = _filter_by_names(d, ["compdev", "excdev"])
        assert set(found.keys()) == {"compdev", "excdev"}
        assert missing == []

    def test_missing_attribute(self):
        d = {"scan": 1}
        found, missing = _filter_by_names(d, ["compdev", "scan"])
        assert found == {"scan": 1}
        assert "compdev" in missing

    def test_dedup(self):
        d = {"compdev": 0.05}
        found, missing = _filter_by_names(d, ["compdev", "CompDev", "compdev"])
        assert len(found) == 1

    def test_empty_names(self):
        found, missing = _filter_by_names({}, [])
        assert found == {}
        assert missing == []


# ---------------------------------------------------------------------------
# _interpret_value
# ---------------------------------------------------------------------------
class TestInterpretValue:
    def test_compressing_ativada(self):
        assert "ativada" in _interpret_value("compressing", 1)

    def test_compressing_desativada(self):
        assert "desativada" in _interpret_value("compressing", 0)

    def test_scan_ligado(self):
        assert "ligado" in _interpret_value("scan", 1)

    def test_scan_desligado(self):
        assert "desligado" in _interpret_value("scan", 0)

    def test_step_degrau(self):
        assert "degrau" in _interpret_value("step", 1)

    def test_step_continuo(self):
        assert "contínuo" in _interpret_value("step", 0)

    def test_excmax_segundos(self):
        assert "300.0 segundos" in _interpret_value("excmax", 300)

    def test_compdev_segundos(self):
        assert "0.05 segundos" in _interpret_value("compdev", 0.05)

    def test_none_value(self):
        assert "não configurado" in _interpret_value("compdev", None)

    def test_vazio_string(self):
        assert "vazio" in _interpret_value("digitalset", "")


# ---------------------------------------------------------------------------
# _format_output
# ---------------------------------------------------------------------------
class TestFormatOutput:
    def test_basic_format(self):
        out = _format_output("TAG_A", {"compdev": 0.05}, [])
        assert "Atributos da tag TAG_A" in out
        assert "compdev:" in out
        assert "Links" not in out

    def test_missing_included(self):
        out = _format_output("TAG_A", {}, ["compdev"])
        assert "não configurado" in out


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo auto (12 atributos)
# ---------------------------------------------------------------------------
class TestGetTagAttributesAuto:
    @pytest.mark.asyncio
    async def test_auto_returns_12(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(tag="LFI_RB3_VAZ_GN_TOTAL")
            assert result["ok"] is True
            assert result["count"] == 12
            assert "compdev" in result["attributes"]
            assert "compdevpercent" in result["attributes"]
            assert "excdev" in result["attributes"]
            assert "excdevpercent" in result["attributes"]
            assert result["output"].startswith("Atributos da tag")
            assert "Links" not in result["output"]


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo compression
# ---------------------------------------------------------------------------
class TestGetTagAttributesCompression:
    @pytest.mark.asyncio
    async def test_compression_returns_5(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attribute_group="compression",
            )
            assert result["ok"] is True
            assert result["count"] == 5
            expected = {"compressing", "compdev", "compdevpercent", "compmin", "compmax"}
            assert set(result["attributes"].keys()) == expected


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo exception
# ---------------------------------------------------------------------------
class TestGetTagAttributesException:
    @pytest.mark.asyncio
    async def test_exception_returns_4(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attribute_group="exception",
            )
            assert result["ok"] is True
            assert result["count"] == 4
            expected = {"excdev", "excdevpercent", "excmin", "excmax"}
            assert set(result["attributes"].keys()) == expected


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo archive
# ---------------------------------------------------------------------------
class TestGetTagAttributesArchive:
    @pytest.mark.asyncio
    async def test_archive_returns_expected(self):
        mock_items = [
            {"Name": "archiving", "Value": 1},
            {"Name": "scan", "Value": 1},
            {"Name": "shutdown", "Value": 0},
            {"Name": "step", "Value": 0},
            {"Name": "future", "Value": 0},
        ]
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": mock_items},
        ):
            result = await get_tag_attributes(
                tag="TAG",
                attribute_group="archive",
            )
            assert result["count"] == 5


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo identity
# ---------------------------------------------------------------------------
class TestGetTagAttributesIdentity:
    @pytest.mark.asyncio
    async def test_identity_returns_expected(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attribute_group="identity",
            )
            assert result["ok"] is True
            assert result["count"] == 7
            assert set(result["attributes"].keys()) == _GROUP_ATTRIBUTES["identity"]


# ---------------------------------------------------------------------------
# get_tag_attributes — alias metadata → identity
# ---------------------------------------------------------------------------
class TestGetTagAttributesMetadataAlias:
    @pytest.mark.asyncio
    async def test_metadata_resolves_to_identity(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            meta = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attribute_group="metadata",
            )
            ident = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attribute_group="identity",
            )
            assert meta["attributes"] == ident["attributes"]


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo scaling
# ---------------------------------------------------------------------------
class TestGetTagAttributesScaling:
    @pytest.mark.asyncio
    async def test_scaling_returns_expected(self):
        mock_items = [
            {"Name": "zero", "Value": 0},
            {"Name": "span", "Value": 100},
            {"Name": "typicalvalue", "Value": 50},
            {"Name": "displaydigits", "Value": 2},
            {"Name": "squareroot", "Value": 0},
            {"Name": "convers", "Value": "1:1"},
        ]
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": mock_items},
        ):
            result = await get_tag_attributes(
                tag="TAG", attribute_group="scaling",
            )
            assert result["count"] == 6


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo interface
# ---------------------------------------------------------------------------
class TestGetTagAttributesInterface:
    @pytest.mark.asyncio
    async def test_interface_returns_expected(self):
        mock_items = [
            {"Name": f"location{i}", "Value": f"LOC{i}"} for i in range(1, 6)
        ] + [
            {"Name": "exdesc", "Value": "EXT"},
            {"Name": "sourcetag", "Value": "SRC"},
            {"Name": "srcptid", "Value": "123"},
        ]
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": mock_items},
        ):
            result = await get_tag_attributes(
                tag="TAG", attribute_group="interface",
            )
            assert result["count"] >= 8


# ---------------------------------------------------------------------------
# get_tag_attributes — attributes explícito sobrepõe grupo
# ---------------------------------------------------------------------------
class TestGetTagAttributesExplicitAttributes:
    @pytest.mark.asyncio
    async def test_explicit_overrides_group(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attributes=["compdev", "excdev"],
            )
            assert result["count"] == 2
            assert set(result["attributes"].keys()) == {"compdev", "excdev"}

    @pytest.mark.asyncio
    async def test_explicit_case_insensitive(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attributes=["CompDev", "EXCDEV"],
            )
            assert result["count"] == 2


# ---------------------------------------------------------------------------
# get_tag_attributes — atributo inexistente
# ---------------------------------------------------------------------------
class TestGetTagAttributesMissing:
    @pytest.mark.asyncio
    async def test_missing_attribute_in_missing_list(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="TAG",
                attributes=["atributo_inexistente"],
            )
            assert result["count"] == 0
            assert "atributo_inexistente" in result["missing_attributes"]
            assert "não configurado" in result["output"]


# ---------------------------------------------------------------------------
# get_tag_attributes — payload vazio
# ---------------------------------------------------------------------------
class TestGetTagAttributesEmptyPayload:
    @pytest.mark.asyncio
    async def test_empty_items(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ):
            result = await get_tag_attributes(tag="TAG")
            assert result["ok"] is False
            assert "Nenhum atributo" in result["output"]
            assert "TAG" in result["output"]


# ---------------------------------------------------------------------------
# get_tag_attributes — tag inexistente (404)
# ---------------------------------------------------------------------------
class TestGetTagAttributesTagNotFound:
    @pytest.mark.asyncio
    async def test_404_returns_controlled_message(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Not Found",
                request=httpx.Request("GET", "http://example.com/points/W/attributes"),
                response=httpx.Response(404),
            ),
        ):
            result = await get_tag_attributes(tag="TAG_INEXISTENTE")
            assert result["ok"] is False
            assert "não encontrada" in result["output"]
            assert "TAG_INEXISTENTE" in result["output"]


# ---------------------------------------------------------------------------
# get_tag_attributes — interpretação de compressão no output
# ---------------------------------------------------------------------------
class TestGetTagAttributesInterpretation:
    @pytest.mark.asyncio
    async def test_compressing_interpreted_as_ativada(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attribute_group="compression",
            )
            assert "ativada" in result["output"]

    @pytest.mark.asyncio
    async def test_scan_interpreted_as_ligado(self):
        with patch(
            "domain.pims.services.tag_attributes_service.get_point_attributes",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await get_tag_attributes(
                tag="LFI_RB3_VAZ_GN_TOTAL",
                attribute_group="auto",
            )
            assert "ligado" in result["output"]


# ---------------------------------------------------------------------------
# get_tag_attributes — grupo inválido → ValueError
# ---------------------------------------------------------------------------
class TestGetTagAttributesInvalidGroup:
    @pytest.mark.asyncio
    async def test_invalid_group_raises(self):
        with pytest.raises(ValueError, match="Grupo 'invalido' inválido"):
            await get_tag_attributes(tag="TAG", attribute_group="invalido")
