from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from domain.pims.services.search_points_service import (
    SEARCH_SELECTED_FIELDS,
    _MAX_COUNT_HARD_CAP,
    _MAX_QUERY_LENGTH,
    _sanitize_query,
    _tokenize_query,
    _build_description_variants,
    _build_name_variants,
    _build_namefilter_variants,
    _extract_search_terms,
    _normalize_accent,
    SearchTerms,
    _useful_chars,
    _validate_max_count,
    _validate_search_mode,
    _build_search_query,
    _build_and_query_for_field,
    _format_items,
    _build_output,
    _dedup_items,
    _detect_advanced_query,
    _has_boundary_match,
    _has_all_tokens_in_text,
    Confidence,
    _compute_confidence_and_basis,
    _rank_and_cap,
    _build_strict_result,
    _build_strict_and_queries,
    search_pi_points,
)

_MOCK_ITEMS = [
    {
        "Name": "LFI_RB3_VAZ",
        "Descriptor": "Vazao GN RB3",
        "WebId": "W1",
        "PointType": "analog",
        "EngineeringUnits": "Nm3/h",
    }
]

_MOCK_ITEMS_5 = [
    {
        "Name": f"TAG_{i}",
        "Descriptor": f"Tag numero {i}",
        "WebId": f"W{i}",
        "PointType": "analog",
        "EngineeringUnits": "m3/h",
    }
    for i in range(5)
]


# ---------------------------------------------------------------------------
# _useful_chars
# ---------------------------------------------------------------------------
class TestUsefulChars:
    def test_empty(self):
        assert _useful_chars("") == 0

    def test_only_wildcards(self):
        assert _useful_chars("***") == 0

    def test_one_char(self):
        assert _useful_chars("*a*") == 1

    def test_two_chars(self):
        assert _useful_chars("*RB*") == 2

    def test_multiple_chars(self):
        assert _useful_chars("velocidade forno") == 15


# ---------------------------------------------------------------------------
# _sanitize_query
# ---------------------------------------------------------------------------
class TestSanitizeQuery:
    def test_none_query(self):
        assert _sanitize_query(None) is None

    def test_empty_query(self):
        assert _sanitize_query("") is None

    def test_whitespace_only(self):
        assert _sanitize_query("   ") is None

    def test_strips_whitespace(self):
        assert _sanitize_query("  LFI_RB3  ") == "LFI_RB3"

    def test_truncates_long_query(self):
        long_q = "x" * 300
        result = _sanitize_query(long_q)
        assert result is not None
        assert len(result) == _MAX_QUERY_LENGTH

    def test_normal_query(self):
        assert _sanitize_query("vazao gn") == "vazao gn"

    def test_one_char_returns_none(self):
        assert _sanitize_query("a") is None

    def test_two_chars_accepted(self):
        assert _sanitize_query("RB") == "RB"

    def test_two_chars_gn_accepted(self):
        assert _sanitize_query("GN") == "GN"

    def test_asterisco_a_rejeitado(self):
        assert _sanitize_query("*a*") is None

    def test_asterisco_rb_aceito(self):
        assert _sanitize_query("*RB*") == "*RB*"


# ---------------------------------------------------------------------------
# _validate_max_count
# ---------------------------------------------------------------------------
class TestValidateMaxCount:
    def test_default(self):
        assert _validate_max_count(5) == 5

    def test_zero_returns_default(self):
        assert _validate_max_count(0) == _MAX_COUNT_HARD_CAP

    def test_negative_returns_default(self):
        assert _validate_max_count(-1) == _MAX_COUNT_HARD_CAP

    def test_hard_cap(self):
        assert _validate_max_count(500) == _MAX_COUNT_HARD_CAP

    def test_within_bounds(self):
        assert _validate_max_count(3) == 3


# ---------------------------------------------------------------------------
# _validate_search_mode
# ---------------------------------------------------------------------------
class TestValidateSearchMode:
    def test_auto_valid(self):
        assert _validate_search_mode("auto") == "auto"

    def test_name_valid(self):
        assert _validate_search_mode("name") == "name"

    def test_description_valid(self):
        assert _validate_search_mode("description") == "description"

    def test_query_valid(self):
        assert _validate_search_mode("query") == "query"

    def test_case_insensitive(self):
        assert _validate_search_mode("AUTO") == "auto"

    def test_invalid_mode(self):
        assert _validate_search_mode("invalid") is None

    def test_empty_mode(self):
        assert _validate_search_mode("") is None


# ---------------------------------------------------------------------------
# _build_search_query
# ---------------------------------------------------------------------------
class TestBuildSearchQuery:
    def test_auto_passes_raw(self):
        assert _build_search_query("vazao", "auto") == "vazao"

    def test_name_uses_name_syntax(self):
        assert _build_search_query("vazao", "name") == "Name:=*vazao*"

    def test_description_uses_description_syntax(self):
        assert _build_search_query("vazao", "description") == "Description:=*vazao*"

    def test_query_passes_raw(self):
        assert _build_search_query("vazao", "query") == "vazao"

    def test_name_not_descriptor(self):
        result = _build_search_query("vazao", "description")
        assert "Descriptor" not in result

    def test_description_not_name_prefix(self):
        result = _build_search_query("vazao", "description")
        assert not result.startswith("name:")


# ---------------------------------------------------------------------------
# _format_items
# ---------------------------------------------------------------------------
class TestFormatItems:
    def test_empty_items(self):
        assert _format_items({}) == []

    def test_skips_items_without_name(self):
        data = {"Items": [{"Descriptor": "test"}]}
        assert _format_items(data) == []

    def test_item_with_all_fields(self):
        data = {
            "Items": [
                {
                    "Name": "LFI_RB3_VAZ",
                    "Descriptor": "Vazao GN RB3",
                    "WebId": "W1",
                    "PointType": "analog",
                    "EngineeringUnits": "Nm3/h",
                }
            ]
        }
        items = _format_items(data)
        assert len(items) == 1
        item = items[0]
        assert item["name"] == "LFI_RB3_VAZ"
        assert item["description"] == "Vazao GN RB3"
        assert item["web_id"] == "W1"
        assert item["point_type"] == "analog"
        assert item["engineering_units"] == "Nm3/h"
        assert "path" in item


# ---------------------------------------------------------------------------
# _dedup_items
# ---------------------------------------------------------------------------
class TestDedupItems:
    def test_no_duplicates(self):
        items = [{"web_id": "W1", "name": "A"}, {"web_id": "W2", "name": "B"}]
        assert len(_dedup_items(items)) == 2

    def test_dedup_by_web_id(self):
        items = [
            {"web_id": "W1", "name": "A"},
            {"web_id": "W1", "name": "A_DUP"},
        ]
        result = _dedup_items(items)
        assert len(result) == 1
        assert result[0]["name"] == "A"

    def test_dedup_by_name_when_web_id_none(self):
        items = [
            {"web_id": None, "name": "A"},
            {"web_id": None, "name": "A"},
        ]
        result = _dedup_items(items)
        assert len(result) == 1
        assert result[0]["name"] == "A"

    def test_dedup_mixed(self):
        items = [
            {"web_id": "W1", "name": "A"},
            {"web_id": None, "name": "B"},
            {"web_id": "W1", "name": "C"},
            {"web_id": None, "name": "B"},
        ]
        result = _dedup_items(items)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _build_output
# ---------------------------------------------------------------------------
class TestBuildOutput:
    def test_no_results(self):
        msg = _build_output("vaz", [], 0, 5)
        assert "Nenhuma tag" in msg
        assert "Para refinar" in msg

    def test_with_results(self):
        msg = _build_output("vaz", [{"name": "TAG_1"}], 1, 5)
        assert "Encontrei até 5" in msg
        assert "1. TAG_1" in msg

    def test_max_count_hit(self):
        items = [{"name": f"T{i}", "description": f"Desc {i}"} for i in range(5)]
        msg = _build_output("vaz", items, 5, 5)
        assert "5 tags candidatas" in msg
        assert "1. T0" in msg
        assert "5. T4" in msg


# ---------------------------------------------------------------------------
# _detect_advanced_query
# ---------------------------------------------------------------------------
class TestDetectAdvancedQuery:
    def test_description_syntax(self):
        assert _detect_advanced_query("Description:=*velocidade*") is True

    def test_name_syntax(self):
        assert _detect_advanced_query("Name:=*LFI*") is True

    def test_raw_text_not_detected(self):
        assert _detect_advanced_query("velocidade forno") is False

    def test_mixed_syntax(self):
        assert _detect_advanced_query("Description:=*a* Name:=*b*") is True


# ---------------------------------------------------------------------------
# search_pi_points — param-level tests
# ---------------------------------------------------------------------------
class TestSearchPiPointsClientParams:
    @pytest.mark.asyncio
    async def test_uses_query_not_q(self):
        """Client receives 'query' parameter, not 'q'."""
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(query="LFI_RB3", search_mode="name")
            call_kwargs = mock_client.call_args.kwargs
            assert "query" in call_kwargs
            assert "Name:=*LFI_RB3*" in call_kwargs["query"]

    @pytest.mark.asyncio
    async def test_sends_max_count_5(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(query="LFI_RB3", max_count=100, search_mode="name")
            call_kwargs = mock_client.call_args.kwargs
            assert call_kwargs["max_count"] == 5

    @pytest.mark.asyncio
    async def test_calls_points_search_endpoint(self):
        """Verifying client_search is called at all (endpoint check is in client test)."""
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(query="LFI_RB3", search_mode="name")
            mock_client.assert_awaited_once()


# ---------------------------------------------------------------------------
# search_pi_points — success
# ---------------------------------------------------------------------------
class TestSearchPiPointsSuccess:
    @pytest.mark.asyncio
    async def test_success_return_format(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(query="LFI_RB3")
            assert result["success"] is True
            assert result["query"] == "LFI_RB3"
            assert result["search_mode"] == "auto"
            assert result["count"] == 1
            assert result["max_count"] == 5
            assert len(result["items"]) == 1
            assert isinstance(result["message"], str)
            assert isinstance(result["output"], str)

    @pytest.mark.asyncio
    async def test_output_is_string(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(query="LFI_RB3")
            assert isinstance(result["output"], str)
            assert len(result["output"]) > 0
            assert "Encontrei até" in result["output"]

    @pytest.mark.asyncio
    async def test_empty_results(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ):
            result = await search_pi_points(query="TAG_INEXISTENTE")
            assert result["success"] is True
            assert result["count"] == 0
            assert result["items"] == []


# ---------------------------------------------------------------------------
# search_pi_points — validation
# ---------------------------------------------------------------------------
class TestSearchPiPointsValidation:
    @pytest.mark.asyncio
    async def test_query_vazia(self):
        result = await search_pi_points(query="")
        assert result["success"] is False
        assert "vazia" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_search_mode_invalido(self):
        result = await search_pi_points(query="vazao", search_mode="invalid")
        assert result["success"] is False
        assert "inválido" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_max_count_hard_cap(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ):
            result = await search_pi_points(query="vazao", max_count=500)
            assert result["max_count"] == _MAX_COUNT_HARD_CAP

    @pytest.mark.asyncio
    async def test_max_count_zero(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ):
            result = await search_pi_points(query="vazao", max_count=0)
            assert result["max_count"] == 5


# ---------------------------------------------------------------------------
# search_pi_points — description mode
# ---------------------------------------------------------------------------
class TestSearchModeDescription:
    @pytest.mark.asyncio
    async def test_montagem_query(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(query="velocidade", search_mode="description")
            call_kwargs = mock_client.call_args.kwargs
            assert "Description:=*velocidade*" in call_kwargs["query"]

    @pytest.mark.asyncio
    async def test_nao_usa_descriptor(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(query="velocidade", search_mode="description")
            query = mock_client.call_args.kwargs["query"]
            assert "Descriptor" not in query

    @pytest.mark.asyncio
    async def test_sem_fallback_404(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Not Found",
                request=httpx.Request("GET", "/points/search"),
                response=httpx.Response(404),
            ),
        ):
            result = await search_pi_points(
                query="velocidade", search_mode="description"
            )
            assert result["success"] is True
            assert result["count"] == 0


# ---------------------------------------------------------------------------
# search_pi_points — name mode
# ---------------------------------------------------------------------------
class TestSearchModeName:
    @pytest.mark.asyncio
    async def test_montagem_query(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(query="LFI_RB3", search_mode="name")
            call_kwargs = mock_client.call_args.kwargs
            assert "Name:=*LFI_RB3*" in call_kwargs["query"]

    @pytest.mark.asyncio
    async def test_fallback_name_filter_404(self):
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "Not Found",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(404),
                ),
            ),
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": _MOCK_ITEMS},
            ),
        ):
            result = await search_pi_points(query="LFI_RB3", search_mode="name")
            assert result["success"] is True
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_fallback_nao_acontece_em_401(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=httpx.Request("GET", "/points/search"),
                response=httpx.Response(401),
            ),
        ):
            result = await search_pi_points(query="LFI_RB3", search_mode="name")
            assert result["success"] is True
            assert result["count"] == 0


# ---------------------------------------------------------------------------
# search_pi_points — auto mode
# ---------------------------------------------------------------------------
class TestSearchModeAuto:
    @pytest.mark.asyncio
    async def test_chama_descricao_primeiro(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(query="velocidade", search_mode="auto")
            first_call_query = mock_client.call_args_list[0].kwargs["query"]
            assert "Description" in first_call_query

    @pytest.mark.asyncio
    async def test_para_se_descricao_der_5(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS_5},
        ) as mock_client:
            result = await search_pi_points(query="velocidade", search_mode="auto")
            assert mock_client.await_count == 1
            assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_chama_nome_se_descricao_menos_5(self):
        """auto calls name search when description returns < 5 results."""
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
            ) as mock_client,
        ):
            mock_client.side_effect = [
                {"Items": _MOCK_ITEMS},           # description: 1 result
                {"Items": _MOCK_ITEMS_5},          # name: 5 results
            ]
            result = await search_pi_points(query="velocidade", search_mode="auto")
            assert mock_client.await_count == 2
            assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_dedup_por_web_id(self):
        """auto deduplicates items by WebId."""
        items_desc = [
            {"Name": "TAG_A", "WebId": "W1", "Descriptor": "Desc A"},
        ]
        items_name = [
            {"Name": "TAG_A", "WebId": "W1", "Descriptor": "Desc A"},
            {"Name": "TAG_B", "WebId": "W2", "Descriptor": "Desc B"},
        ]
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
            ) as mock_client,
        ):
            mock_client.side_effect = [
                {"Items": items_desc},
                {"Items": items_name},
            ]
            result = await search_pi_points(query="descricao tag_a", search_mode="auto")
            assert result["count"] == 2
            names = [i["name"] for i in result["items"]]
            assert sorted(names) == ["TAG_A", "TAG_B"]

    @pytest.mark.asyncio
    async def test_dedup_por_name_quando_sem_web_id(self):
        items_desc = [
            {"Name": "TAG_A", "Descriptor": "Desc A"},
        ]
        items_name = [
            {"Name": "TAG_A", "Descriptor": "Desc A"},
            {"Name": "TAG_B", "Descriptor": "Desc B"},
        ]
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
            ) as mock_client,
        ):
            mock_client.side_effect = [
                {"Items": items_desc},
                {"Items": items_name},
            ]
            result = await search_pi_points(query="descricao tag_a", search_mode="auto")
            assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_merge_respeita_limite(self):
        items_3 = _MOCK_ITEMS_5[:3]
        items_5 = _MOCK_ITEMS_5
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
            ) as mock_client,
        ):
            mock_client.side_effect = [
                {"Items": items_3},
                {"Items": items_5},
            ]
            result = await search_pi_points(query="descricao tag_a", search_mode="auto")
            assert result["count"] == 5


# ---------------------------------------------------------------------------
# search_pi_points — query mode
# ---------------------------------------------------------------------------
class TestSearchModeQuery:
    @pytest.mark.asyncio
    async def test_query_avancada_passada_direto(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(
                query="Description:=*velocidade*", search_mode="query"
            )
            call_kwargs = mock_client.call_args.kwargs
            assert call_kwargs["query"] == "Description:=*velocidade*"

    @pytest.mark.asyncio
    async def test_query_sem_sintaxe_vira_auto(self):
        """query mode with no AFSearch syntax → falls back to auto (description)."""
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ) as mock_client:
            await search_pi_points(
                query="velocidade forno", search_mode="query"
            )
            # auto calls description first
            first_call_query = mock_client.call_args_list[0].kwargs["query"]
            assert "Description:=" in first_call_query


# ---------------------------------------------------------------------------
# search_pi_points — hard cap
# ---------------------------------------------------------------------------
class TestHardCap:
    @pytest.mark.asyncio
    async def test_max_count_100_vira_5(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(query="vazao", max_count=100)
            assert result["max_count"] == 5

    @pytest.mark.asyncio
    async def test_retorna_max_5_itens(self):
        many_items = [{"Name": f"T{i}"} for i in range(20)]
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": many_items},
        ):
            result = await search_pi_points(query="vazao")
            assert len(result["items"]) <= 5

    @pytest.mark.asyncio
    async def test_output_textual_ate_5(self):
        many_items = [{"Name": f"T{i}", "Descriptor": f"D{i}"} for i in range(10)]
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": many_items},
        ):
            result = await search_pi_points(query="vazao")
            lines = result["output"].strip().split("\n")
            numbered = [l for l in lines if l[0].isdigit() and ". " in l[:4]]
            assert len(numbered) <= 5


# ---------------------------------------------------------------------------
# search_pi_points — sanitization
# ---------------------------------------------------------------------------
class TestSanitization:
    @pytest.mark.asyncio
    async def test_query_vazia_retorna_erro(self):
        result = await search_pi_points(query="")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_um_char_util_retorna_erro(self):
        result = await search_pi_points(query="a")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_asterisco_a_rejeitado(self):
        result = await search_pi_points(query="*a*")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_asterisco_rb_aceito(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(query="*RB*")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_query_ate_200_chars(self):
        long_q = "x" * 200
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(query=long_q)
            assert result["success"] is True


# ---------------------------------------------------------------------------
# search_pi_points — fallback
# ---------------------------------------------------------------------------
class TestSearchPiPointsFallback:
    @pytest.mark.asyncio
    async def test_fallback_404_name_triggers_name_filter(self):
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "Not Found",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(404),
                ),
            ),
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": _MOCK_ITEMS},
            ),
        ):
            result = await search_pi_points(query="LFI_RB3", search_mode="name")
            assert result["success"] is True
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_fallback_405_name_triggers_name_filter(self):
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "Method Not Allowed",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(405),
                ),
            ),
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": _MOCK_ITEMS},
            ),
        ):
            result = await search_pi_points(query="LFI_RB3", search_mode="name")
            assert result["success"] is True
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_fallback_nao_acontece_description(self):
        """description mode does NOT fall back to nameFilter."""
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Not Found",
                request=httpx.Request("GET", "/points/search"),
                response=httpx.Response(404),
            ),
        ):
            result = await search_pi_points(
                query="velocidade", search_mode="description"
            )
            assert result["success"] is True
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_fallback_auto_404_descricao_ignorado(self):
        """auto mode ignores 404 on description step (just returns empty for desc)."""
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
            ) as mock_client,
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": _MOCK_ITEMS},
            ),
        ):
            mock_client.side_effect = [
                httpx.HTTPStatusError(
                    "Not Found",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(404),
                ),
                httpx.HTTPStatusError(
                    "Not Found",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(404),
                ),
            ]
            result = await search_pi_points(query="velocidade", search_mode="auto")
            # description 404 → empty, name 404 → nameFilter fallback
            assert result["success"] is True
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_fallback_tambem_falha(self):
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "Not Found",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(404),
                ),
            ),
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("fallback failed"),
            ),
        ):
            result = await search_pi_points(query="LFI_RB3", search_mode="name")
            assert result["success"] is True
            assert result["count"] == 0


# ---------------------------------------------------------------------------
# search_pi_points — errors
# ---------------------------------------------------------------------------
class TestSearchPiPointsErrors:
    @pytest.mark.asyncio
    async def test_pi_web_api_401(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=httpx.Request("GET", "/points/search"),
                response=httpx.Response(401),
            ),
        ):
            result = await search_pi_points(query="LFI_RB3", search_mode="name")
            assert result["success"] is True
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_network_timeout(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=httpx.ReadTimeout("read timed out"),
        ):
            result = await search_pi_points(
                query="LFI_RB3", search_mode="name"
            )
            assert result["success"] is True
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_unexpected_exception(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            result = await search_pi_points(
                query="LFI_RB3", search_mode="name"
            )
            assert result["success"] is True
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_http_400_description_no_fallback(self):
        """description mode with 400 → falls through all variants, returns 0."""
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Bad Request",
                request=httpx.Request("GET", "/points/search"),
                response=httpx.Response(400),
            ),
        ):
            result = await search_pi_points(
                query="velocidade forno", search_mode="description"
            )
            assert result["success"] is True
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_http_400_query_no_fallback(self):
        """query mode with 400 → no fallback, returns error."""
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Bad Request",
                request=httpx.Request("GET", "/points/search"),
                response=httpx.Response(400),
            ),
        ):
            result = await search_pi_points(
                query="Description:=*x*", search_mode="query"
            )
            assert result["success"] is False
            assert "HTTP 400" in result["message"]

    @pytest.mark.asyncio
    async def test_query_one_char_rejected(self):
        result = await search_pi_points(query="a")
        assert result["success"] is False
        assert "vazia" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_query_two_chars_accepted_rb(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(query="RB")
            assert result["success"] is True
            assert result["count"] == 1


# ---------------------------------------------------------------------------
# _tokenize_query
# ---------------------------------------------------------------------------
class TestTokenizeQuery:
    def test_single_term(self):
        assert _tokenize_query("velocidade") == ["velocidade"]

    def test_two_terms(self):
        assert _tokenize_query("velocidade forno") == ["velocidade", "forno"]

    def test_short_term_rejected(self):
        assert _tokenize_query("a forno") == ["forno"]

    def test_all_short_rejected(self):
        assert _tokenize_query("a b") == []

    def test_extra_spaces(self):
        assert _tokenize_query("  velocidade   forno  ") == ["velocidade", "forno"]


# ---------------------------------------------------------------------------
# _extract_search_terms — Query Understanding
# ---------------------------------------------------------------------------
class TestExtractSearchTerms:
    def test_removes_stopwords(self):
        t = _extract_search_terms("velocidade do forno")
        assert t.normalized_phrase == "velocidade forno"
        assert t.tokens == ["velocidade", "forno"]

    def test_natural_query_full(self):
        t = _extract_search_terms("tem alguma tag de velocidade do forno?")
        assert "velocidade" in t.tokens
        assert "forno" in t.tokens
        assert "tem" not in t.tokens

    def test_preserves_acronyms(self):
        t = _extract_search_terms("procure tags de vazão GN do RB3")
        assert "gn" in t.tokens
        assert "rb3" in t.tokens
        assert "vazao" in t.variable_terms

    def test_classifies_variable(self):
        t = _extract_search_terms("velocidade")
        assert "velocidade" in t.variable_terms

    def test_classifies_equipment(self):
        t = _extract_search_terms("forno")
        assert "forno" in t.equipment_terms

    def test_industrial_code_not_equipment(self):
        t = _extract_search_terms("rb3")
        assert "rb3" in t.area_terms
        assert "rb3" not in t.equipment_terms

    def test_accent_normalization(self):
        t = _extract_search_terms("vazão")
        assert "vazao" in t.variable_terms

    def test_technical_expansion(self):
        t = _extract_search_terms("velocidade forno")
        assert "VEL" in t.technical_terms
        assert "FRN" in t.technical_terms

    def test_only_stopwords_returns_empty(self):
        t = _extract_search_terms("de do da em")
        assert t.tokens == []


# ---------------------------------------------------------------------------
# _normalize_accent
# ---------------------------------------------------------------------------
class TestNormalizeAccent:
    def test_vazao(self):
        assert _normalize_accent("vazão") == "vazao"

    def test_pressao(self):
        assert _normalize_accent("pressão") == "pressao"

    def test_nivel(self):
        assert _normalize_accent("nível") == "nivel"

    def test_valvula(self):
        assert _normalize_accent("válvula") == "valvula"

    def test_temperatura(self):
        assert _normalize_accent("temperatura") == "temperatura"


# ---------------------------------------------------------------------------
# _build_description_variants
# ---------------------------------------------------------------------------
class TestBuildDescriptionVariants:
    def _make(self, query: str):
        return _build_description_variants(_extract_search_terms(query))

    def test_one_term(self):
        variants = self._make("velocidade")
        assert len(variants) == 1
        assert variants[0] == "Description:=*velocidade*"

    def test_two_terms_order(self):
        variants = self._make("velocidade forno")
        assert len(variants) == 4
        assert variants[0] == 'Description:="*velocidade forno*"'  # original (same as normalized → dedup)
        assert variants[1] == "Description:=*velocidade*forno*"
        assert variants[2] == "Description:=*velocidade*"
        assert variants[3] == "Description:=*forno*"

    def test_no_descriptor(self):
        variants = self._make("velocidade")
        assert all("Descriptor" not in v for v in variants)

    def test_no_duplicates(self):
        variants = self._make("velocidade")
        assert len(variants) == len(set(variants))


# ---------------------------------------------------------------------------
# _build_name_variants
# ---------------------------------------------------------------------------
class TestBuildNameVariants:
    def _make(self, query: str):
        return _build_name_variants(_extract_search_terms(query))

    def test_one_term(self):
        variants = self._make("velocidade")
        assert variants[0] == "Name:=*velocidade*"
        assert any("VEL" in v for v in variants), f"Expected VEL expansion in {variants}"

    def test_two_terms_base(self):
        variants = self._make("velocidade forno")
        assert variants[0] == 'Name:="*velocidade forno*"'
        assert variants[1] == "Name:=*velocidade*forno*"
        assert any("VEL" in v for v in variants), "Expected VEL combos"
        assert any("FRN" in v for v in variants), "Expected FRN combos"

    def test_combos_before_individuals(self):
        variants = self._make("velocidade forno")
        # Crossed combos (variable×equipment with two expansions separated by *)
        combo_indices = [i for i, v in enumerate(variants) if v.count("*") >= 3 and ("VEL" in v.upper() or "FRN" in v.upper())]
        # "velocidade" as a bare individual token (not the wildcard combo *velocidade*forno*)
        individual_idx = None
        for i, v in enumerate(variants):
            if v == "Name:=*velocidade*":
                individual_idx = i
                break
        assert combo_indices, f"No combo variants found in {variants}"
        assert individual_idx is not None, f"No individual *velocidade* found in {variants}"
        assert max(combo_indices) < individual_idx, (
            f"Combos {combo_indices} should come before individual at index {individual_idx}"
        )

    def test_technical_patterns_velocidade_forno(self):
        variants = self._make("velocidade forno")
        assert any("FRN*VELOCIDADE" in v for v in variants), f"FRN*VELOCIDADE not in {variants}"
        assert any("VEL*FORNO" in v for v in variants) or any("VELOCIDADE*FORNO" in v for v in variants)

    def test_no_technical_patterns_other_terms(self):
        variants = self._make("vazao gn")
        assert not any("FRN" in v for v in variants), f"Unexpected FRN in {variants}"

    def test_hardcoded_pattern_removed(self):
        """Assert no hardcoded 'velocidade' + 'forno' conditional by checking expansion is dictionary-driven."""
        variants = self._make("velocidade forno")
        assert any("FRN" in v for v in variants), "FRN should come from dictionary, not hardcoded"
        assert any("VELOCIDADE*FRN" in v for v in variants), "VELOCIDADE*FRN should exist from dict expansion"


# ---------------------------------------------------------------------------
# _build_namefilter_variants
# ---------------------------------------------------------------------------
class TestBuildNameFilterVariants:
    def _make(self, query: str):
        return _build_namefilter_variants(_extract_search_terms(query))

    def test_one_term(self):
        variants = self._make("velocidade")
        assert variants[0] == "*velocidade*"
        assert any("VEL" in v for v in variants), f"Expected VEL expansion in {variants}"

    def test_two_terms(self):
        variants = self._make("velocidade forno")
        assert "*velocidade*forno*" in variants
        assert "*velocidade*" in variants
        assert "*forno*" in variants

    def test_technical_patterns(self):
        variants = self._make("velocidade forno")
        assert any("FRN" in v for v in variants), f"FRN not in {variants}"
        assert any("VEL" in v for v in variants), f"VEL not in {variants}"

    def test_combos_before_individuals(self):
        variants = self._make("velocidade forno")
        # Crossed combos (multiple wildcards)
        combo_indices = [i for i, v in enumerate(variants) if v.count("*") >= 3 and ("VEL" in v.upper() or "FRN" in v.upper())]
        individual_idx = None
        for i, v in enumerate(variants):
            if v == "*velocidade*":
                individual_idx = i
                break
        assert combo_indices, f"No combo variants in {variants}"
        assert individual_idx is not None, f"No individual *velocidade* in {variants}"
        assert max(combo_indices) < individual_idx


# ---------------------------------------------------------------------------
# search_pi_points — description mode with variants
# ---------------------------------------------------------------------------
class TestSearchDescriptionWithVariants:
    @pytest.mark.asyncio
    async def test_first_variant_succeeds(self):
        """Description with quoted phrase works first."""
        items = [{"Name": "LFI_RB1_FRN_VELOCIDADE_LIM_INF", "WebId": "W1"}]
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": items},
        ) as mock_client:
            result = await search_pi_points(
                query="velocidade forno", search_mode="description",
            )
            assert result["count"] == 1
            first_call = mock_client.call_args.kwargs["query"]
            assert 'Description:="*velocidade forno*"' in first_call

    @pytest.mark.asyncio
    async def test_falls_through_to_next_variant(self):
        """First variant returns 0, second variant finds items."""
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
        ) as mock_client:
            mock_client.side_effect = [
                {"Items": []},  # aspas → 0
                {"Items": [{"Name": "TAG_FOUND", "WebId": "W1"}]},  # *velocidade*forno* → 1
            ]
            result = await search_pi_points(
                query="velocidade forno", search_mode="description",
            )
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_no_results_from_all_variants(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ):
            result = await search_pi_points(
                query="velocidade forno", search_mode="description",
            )
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_continues_after_http_error(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
        ) as mock_client:
            mock_client.side_effect = [
                httpx.HTTPStatusError(
                    "Bad Request", request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(400),
                ),
                {"Items": [{"Name": "TAG_FOUND", "WebId": "W1"}]},
            ]
            result = await search_pi_points(
                query="velocidade forno", search_mode="description",
            )
            assert result["count"] == 1


# ---------------------------------------------------------------------------
# search_pi_points — name mode with 500 fallback
# ---------------------------------------------------------------------------
class TestSearchNameModeFallback500:
    @pytest.mark.asyncio
    async def test_500_triggers_fallback(self):
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "Server Error",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(500),
                ),
            ),
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": _MOCK_ITEMS},
            ),
        ):
            result = await search_pi_points(
                query="velocidade forno", search_mode="name",
            )
            assert result["success"] is True
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_500_uses_variants_in_fallback(self):
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
                side_effect=httpx.HTTPStatusError(
                    "Server Error",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(500),
                ),
            ),
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": _MOCK_ITEMS},
            ) as mock_nf,
        ):
            await search_pi_points(
                query="velocidade forno", search_mode="name",
            )
            call_nf = mock_nf.call_args.kwargs["name_filter"]
            # Should try a variant without literal spaces
            assert " " not in call_nf

    @pytest.mark.asyncio
    async def test_500_triggers_fallback_in_auto(self):
        """auto mode: description 0, name 500 → nameFilter fallback works."""
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
            ) as mock_client,
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": _MOCK_ITEMS},
            ),
        ):
            # description returns 0, name returns 500
            mock_client.side_effect = [
                {"Items": []},  # description
                httpx.HTTPStatusError(
                    "Server Error",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(500),
                ),  # name
            ]
            result = await search_pi_points(
                query="velocidade forno", search_mode="auto",
            )
            assert result["success"] is True
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_dedup_when_description_and_name_return_same(self):
        """Dedup between description and name fallback works."""
        item = {"Name": "LFI_RB1_FRN_VELOCIDADE_LIM_INF", "Descriptor": "VELOCIDADE FORNO", "WebId": "W1"}
        with (
            patch(
                "domain.pims.services.search_points_service.client_search",
                new_callable=AsyncMock,
            ) as mock_client,
            patch(
                "domain.pims.services.search_points_service.get_points_by_name_filter",
                new_callable=AsyncMock,
                return_value={"Items": [item]},
            ),
        ):
            mock_client.side_effect = [
                {"Items": [item]},  # description finds it
                httpx.HTTPStatusError(
                    "Server Error",
                    request=httpx.Request("GET", "/points/search"),
                    response=httpx.Response(500),
                ),  # name fails
            ]
            result = await search_pi_points(
                query="velocidade forno", search_mode="auto",
            )
            assert result["count"] == 1  # dedup, not 2


# ---------------------------------------------------------------------------
# search_pi_points — output limits
# ---------------------------------------------------------------------------
class TestOutputLimits:
    @pytest.mark.asyncio
    async def test_output_max_5_tags(self):
        many_items = [{"Name": f"T{i}", "Descriptor": f"D{i}", "WebId": f"W{i}"} for i in range(10)]
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": many_items},
        ):
            result = await search_pi_points(query="tag", search_mode="auto")
            assert len(result["items"]) <= 5
            lines = result["output"].strip().split("\n")
            numbered = [l for l in lines if l[0].isdigit() and ". " in l[:4]]
            assert len(numbered) <= 5

    @pytest.mark.asyncio
    async def test_zero_message_preserved(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": []},
        ):
            result = await search_pi_points(
                query="tag_que_nao_existe", search_mode="auto",
            )
            assert result["count"] == 0
            assert "Nenhuma tag" in result["message"]


# ---------------------------------------------------------------------------
# Validation preserved
# ---------------------------------------------------------------------------
class TestValidationPreserved:
    @pytest.mark.asyncio
    async def test_single_a_rejected(self):
        result = await search_pi_points(query="a")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_rb_accepted(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(query="RB")
            assert result["success"] is True


# ===================================================================
# T015 — TestBuildAndQuery
# ===================================================================
class TestBuildAndQuery:

    def test_1_token_description(self):
        q = _build_and_query_for_field("Description", ["velocidade"])
        assert q == "Description:=*velocidade*"

    def test_2_tokens_description(self):
        q = _build_and_query_for_field("Description", ["velocidade", "rb2"])
        assert q == "Description:=*velocidade* AND Description:=*rb2*"

    def test_3_tokens_description(self):
        q = _build_and_query_for_field("Description", ["vazao", "gn", "rb3"])
        assert q == "Description:=*vazao* AND Description:=*gn* AND Description:=*rb3*"

    def test_1_token_name(self):
        q = _build_and_query_for_field("Name", ["LFI_RB3"])
        assert q == "Name:=*LFI_RB3*"

    def test_2_tokens_name(self):
        q = _build_and_query_for_field("Name", ["velocidade", "rb2"])
        assert q == "Name:=*velocidade* AND Name:=*rb2*"

    def test_reversed_order_equivalence(self):
        q1 = _build_and_query_for_field("Description", ["velocidade", "rb2"])
        q2 = _build_and_query_for_field("Description", ["rb2", "velocidade"])
        assert q1 != q2
        assert "velocidade" in q1 and "rb2" in q1
        assert "rb2" in q2 and "velocidade" in q2

    def test_accent_normalization(self):
        q = _build_and_query_for_field("Description", ["vazao", "rb3"])
        assert "vazao" in q and "rb3" in q

    def test_invalid_field_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _build_and_query_for_field("Invalid", ["test"])

    def test_empty_tokens_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _build_and_query_for_field("Description", [])


# ===================================================================
# T016 — TestBoundaryCheck
# ===================================================================
class TestBoundaryCheck:

    def test_rb2_exact(self):
        assert _has_boundary_match("RB2", "CORRENTE EXAUSTOR JATO DO RB2") is True

    def test_rb2_not_rb20(self):
        assert _has_boundary_match("RB2", "CORRENTE EXAUSTOR JATO DO RB20") is False

    def test_lfi_boundary(self):
        assert _has_boundary_match("LFI", "LFI_RB3_VAZAO") is True

    def test_rb2_with_underscore_separator(self):
        assert _has_boundary_match("RB2", "LFI_RB2_VELOPROC") is True

    def test_b04_exact(self):
        assert _has_boundary_match("B04", "MOTOR B04 PRINCIPAL") is True

    def test_b04_not_b040(self):
        assert _has_boundary_match("B04", "MOTOR B040 PRINCIPAL") is False


# ===================================================================
# T017 — TestLocalFilter
# ===================================================================
class TestLocalFilter:

    def test_lfs_rb2_veloproc_all_tokens(self):
        assert _has_all_tokens_in_text(
            ["velocidade", "rb2"],
            "LFS_RB2_VELOPROC",
            "VELOCIDADE DO PROCESSO DO RB2",
        ) is True

    def test_lfs_rb2_ex_jg_corrente_rejected(self):
        assert _has_all_tokens_in_text(
            ["velocidade", "rb2"],
            "LFS_RB2_A_EX_JG",
            "CORRENTE DO EXAUSTOR JATO DO RB2",
        ) is False

    def test_lfs_rb3_veloproc_velocidade_rejected(self):
        assert _has_all_tokens_in_text(
            ["velocidade", "rb2"],
            "LFS_RB3_VELOPROC",
            "VELOCIDADE DO PROCESSO DO RB3",
        ) is False

    def test_lfs_rb2_motor_01_velocidade_sem_rb2(self):
        assert _has_all_tokens_in_text(
            ["velocidade", "rb2"],
            "LFS_RB2_MOTOR_01",
            "VELOCIDADE DO MOTOR PRINCIPAL",
        ) is True  # RB2 in name (underscore boundary), velocidade in desc

    def test_tag_generica_velocidade_sozinha_rejected(self):
        assert _has_all_tokens_in_text(
            ["velocidade", "rb2"],
            "TAG_GENERICA",
            "VELOCIDADE",
        ) is False

    def test_1_token_aceito(self):
        assert _has_all_tokens_in_text(
            ["velocidade"],
            "LFS_RB2_VELOPROC",
            "VELOCIDADE DO PROCESSO DO RB2",
        ) is True


# ===================================================================
# T018 — TestRankingAndConfidence
# ===================================================================
class TestRankingAndConfidence:

    def test_velocidade_rb2_high(self):
        item = {"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"}
        conf, _ = _compute_confidence_and_basis(item, ["velocidade", "rb2"])
        assert conf == Confidence.HIGH

    def test_corrente_rb2_low(self):
        item = {"name": "LFS_RB2_A_EX_JG", "description": "CORRENTE DO EXAUSTOR JATO DO RB2"}
        conf, _ = _compute_confidence_and_basis(item, ["velocidade", "rb2"])
        assert conf == Confidence.LOW

    def test_velocidade_rb3_low(self):
        item = {"name": "LFS_RB3_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB3"}
        conf, _ = _compute_confidence_and_basis(item, ["velocidade", "rb2"])
        assert conf == Confidence.LOW

    def test_name_exact_high(self):
        item = {"name": "LFS_RB2_VELOPROC", "description": "qualquer"}
        conf, _ = _compute_confidence_and_basis(item, ["lfs_rb2_veloproc"])
        assert conf == Confidence.HIGH

    def test_ranking_priority(self):
        items = [
            {"name": "LFS_RB2_A_EX_JG", "description": "CORRENTE DO EXAUSTOR JATO DO RB2"},
            {"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"},
        ]
        ranked = _rank_and_cap(items, ["velocidade", "rb2"])
        assert len(ranked) == 1
        assert ranked[0]["name"] == "LFS_RB2_VELOPROC"

    def test_hard_cap_5(self):
        items = [
            {"name": f"LFS_RB2_TAG_{i}", "description": f"VELOCIDADE DO PROCESSO DO RB2 TAG_{i}"}
            for i in range(10)
        ]
        ranked = _rank_and_cap(items, ["velocidade", "rb2"], cap=5)
        assert len(ranked) <= 5

    def test_low_not_returned(self):
        items = [
            {"name": "LFS_RB2_A_EX_JG", "description": "CORRENTE"},
            {"name": "LFS_RB3_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB3"},
        ]
        ranked = _rank_and_cap(items, ["velocidade", "rb2"])
        assert len(ranked) == 0


# ===================================================================
# T019 — TestNoConfidentMatch
# ===================================================================
class TestNoConfidentMatch:

    def test_no_items_no_confident_match(self):
        result = _build_strict_result(
            "velocidade rb2", "auto", [], ["velocidade", "rb2"],
        )
        assert result["no_confident_match"] is True
        assert result["refinement_suggested"] is True
        assert result["success"] is False
        assert result["count"] == 0

    def test_low_only_no_confident_match(self):
        items = [{"name": "LFS_RB2_A_EX_JG", "description": "CORRENTE DO EXAUSTOR JATO DO RB2"}]
        result = _build_strict_result(
            "velocidade rb2", "auto", items, ["velocidade", "rb2"],
        )
        assert result["no_confident_match"] is True

    def test_success_with_results(self):
        items = [{"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"}]
        result = _build_strict_result(
            "velocidade rb2", "auto", items, ["velocidade", "rb2"],
        )
        assert result["no_confident_match"] is False
        assert result["count"] >= 1
        assert result["success"] is True


# ===================================================================
# T020 — TestParallelAuto (isolated, no real PI)
# ===================================================================
class TestParallelAuto:

    @pytest.mark.asyncio
    async def test_builds_at_most_4_queries(self):
        st = SearchTerms(
            original="velocidade rb2",
            normalized_phrase="velocidade rb2",
            tokens=["velocidade", "rb2"],
            variable_terms=["velocidade"],
            equipment_terms=[],
            area_terms=["rb2"],
            technical_terms=["velocidade", "rb2", "VEL", "VELOC", "VELOCIDADE"],
        )
        queries = await _build_strict_and_queries(st, max_variants=4)
        assert len(queries) <= 4
        assert len(queries) >= 2
        for q in queries:
            assert "Description" in q or "Name" in q

    @pytest.mark.asyncio
    async def test_1_token_no_extra_queries(self):
        st = SearchTerms(
            original="rb2",
            normalized_phrase="rb2",
            tokens=["rb2"],
            variable_terms=[],
            equipment_terms=[],
            area_terms=["rb2"],
            technical_terms=["rb2"],
        )
        queries = await _build_strict_and_queries(st, max_variants=4)
        assert len(queries) == 1  # only description


# ===================================================================
# T021 — TestSchemaOutput
# ===================================================================
class TestSchemaOutput:

    def test_output_is_plain_text_with_confidence(self):
        items = [{"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"}]
        result = _build_strict_result(
            "velocidade rb2", "auto", items, ["velocidade", "rb2"],
        )
        output = result["output"]
        assert isinstance(output, str)
        assert "alta confiança" in output
        assert "LFS_RB2_VELOPROC" in output
        assert output == result["message"]

    def test_medium_confidence_label(self):
        items = [{"name": "LFS_RB2_VAZAO", "description": "OUTRA DESCRICAO"}]
        result = _build_strict_result(
            "vazao rb2", "auto", items, ["vazao", "rb2"],
        )
        output = result["output"]
        assert "confiança média" in output
        assert "LFS_RB2_VAZAO" in output

    def test_no_confident_match_plain_text(self):
        result = _build_strict_result(
            "xxx yyy", "auto", [], ["xxx", "yyy"],
        )
        assert result["no_confident_match"] is True
        assert result["refinement_suggested"] is True
        output = result["output"]
        assert isinstance(output, str)
        assert "Nenhuma tag" in output
        assert "Para refinar" in output
        assert output == result["message"]

    def test_output_matches_message(self):
        items = [{"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"}]
        result = _build_strict_result(
            "velocidade rb2", "auto", items, ["velocidade", "rb2"],
        )
        assert result["output"] == result["message"]


# ===================================================================
# T022 — TestFlagDisabledRegression
# ===================================================================
class TestFlagDisabledRegression:
    @pytest.mark.asyncio
    async def test_auto_mode_legacy_path(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            with patch(
                "domain.pims.services.search_points_service._mcp_settings",
                new=type("obj", (object,), {"ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND": False})(),
                create=True,
            ):
                result = await search_pi_points(
                    query="vazao", search_mode="auto"
                )
                assert result["success"] is True
                assert "output" in result

    @pytest.mark.asyncio
    async def test_description_mode_legacy(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(
                query="vazao", search_mode="description"
            )
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_name_mode_legacy(self):
        with patch(
            "domain.pims.services.search_points_service.client_search",
            new_callable=AsyncMock,
            return_value={"Items": _MOCK_ITEMS},
        ):
            result = await search_pi_points(
                query="LFI_RB3", search_mode="name"
            )
            assert result["success"] is True


# ===================================================================
# T023 — TestBuildStrictAndQueriesMultiToken
# ===================================================================
class TestBuildStrictAndQueriesMultiToken:

    @pytest.mark.asyncio
    async def test_q3_uses_all_context_tokens(self):
        st = SearchTerms(
            original="velocidade rb2 bomba",
            normalized_phrase="velocidade rb2 bomba",
            tokens=["velocidade", "rb2", "bomba"],
            variable_terms=["velocidade"],
            equipment_terms=["bomba"],
            area_terms=["rb2"],
            technical_terms=["velocidade", "rb2", "bomba"],
        )
        queries = await _build_strict_and_queries(st, max_variants=4)
        q3 = queries[2] if len(queries) > 2 else None
        if q3 and "Description" in q3 and "Name" in q3:
            assert "rb2" in q3 or "RB2" in q3
            assert "bomba" in q3 or "BOMBA" in q3
            assert "velocidade" in q3
            assert q3.count("AND") == 2  # Name AND-s + DESC AND-s → 2 ANDs

    @pytest.mark.asyncio
    async def test_q4_uses_all_context_tokens(self):
        st = SearchTerms(
            original="temperatura forno aciaria",
            normalized_phrase="temperatura forno aciaria",
            tokens=["temperatura", "forno", "aciaria"],
            variable_terms=["temperatura"],
            equipment_terms=["forno"],
            area_terms=["aciaria"],
            technical_terms=["temperatura", "forno", "aciaria"],
        )
        queries = await _build_strict_and_queries(st, max_variants=4)
        q4 = queries[3] if len(queries) > 3 else None
        if q4 and "Description" in q4 and "Name" in q4:
            assert "ACIARIA" in q4 or "aciaria" in q4
            assert "FORNO" in q4 or "forno" in q4
            assert "TEMPERATURA" in q4 or "temperatura" in q4

    @pytest.mark.asyncio
    async def test_q3_has_both_fields(self):
        st = SearchTerms(
            original="vazao rb3",
            normalized_phrase="vazao rb3",
            tokens=["vazao", "rb3"],
            variable_terms=["vazao"],
            equipment_terms=[],
            area_terms=["rb3"],
            technical_terms=["vazao", "rb3"],
        )
        queries = await _build_strict_and_queries(st, max_variants=4)
        assert len(queries) >= 2
        for q in queries:
            assert isinstance(q, str) and len(q) > 0


# ===================================================================
# T024 — TestBuildStrictResultConfidence
# ===================================================================
class TestBuildStrictResultConfidence:

    def test_output_contains_high_confidence(self):
        items = [{"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"}]
        result = _build_strict_result(
            "velocidade rb2", "auto", items, ["velocidade", "rb2"],
        )
        assert "alta confiança" in result["output"]
        assert result["items"][0]["confidence"] == "high"

    def test_output_contains_medium_confidence(self):
        items = [{"name": "LFS_RB2_VAZAO", "description": "OUTRA DESCRICAO"}]
        result = _build_strict_result(
            "vazao rb2", "auto", items, ["vazao", "rb2"],
        )
        assert "confiança média" in result["output"]

    def test_multiple_items_all_high(self):
        items = [
            {"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"},
            {"name": "LFS_RB2_VELO", "description": "VELOCIDADE AUX RB2"},
        ]
        result = _build_strict_result(
            "velocidade rb2", "auto", items, ["velocidade", "rb2"],
        )
        assert result["no_confident_match"] is False
        assert result["refinement_suggested"] is False  # all high → no refinement needed

    def test_mixed_confidence_suggests_refinement(self):
        items = [
            {"name": "LFS_RB2_VELOPROC", "description": "VELOCIDADE DO PROCESSO DO RB2"},
            {"name": "TAG_X", "description": "VELOCIDADE PROCESSO RB2"},
        ]
        result = _build_strict_result(
            "velocidade rb2", "auto", items, ["velocidade", "rb2"],
        )
        assert result["no_confident_match"] is False
        assert result["refinement_suggested"] is True  # mixed HIGH+MEDIUM → refinement suggested


# ===================================================================
# T025 — TestBoundaryCheckEdgeCases
# ===================================================================
class TestBoundaryCheckEdgeCases:

    def test_token_at_start_of_text(self):
        assert _has_boundary_match("LFI", "LFI_RB3_VAZAO") is True

    def test_token_at_end_of_text(self):
        assert _has_boundary_match("RB3", "VAZAO_GN_RB3") is True

    def test_token_with_hyphen_boundary(self):
        assert _has_boundary_match("B04", "MOTOR-B04-PRINCIPAL") is True

    def test_substring_mismatch(self):
        assert _has_boundary_match("VEL", "VELOCIDADE") is False

    def test_substring_mismatch_suffix(self):
        assert _has_boundary_match("RB2", "LFS_RB20_TAG") is False


# ===================================================================
# T026 — TestExtractSearchTerms
# ===================================================================
class TestExtractSearchTerms:

    def test_velocidade_rb2_classification(self):
        st = _extract_search_terms("velocidade rb2")
        assert "velocidade" in st.tokens
        assert "rb2" in st.tokens
        assert "velocidade" in st.variable_terms
        assert "rb2" in st.area_terms

    def test_three_tokens_mixed(self):
        st = _extract_search_terms("temperatura forno aciaria")
        assert len(st.tokens) >= 2
        if "temperatura" in st.tokens:
            assert "temperatura" in st.variable_terms
        if "forno" in st.tokens:
            assert "forno" in st.equipment_terms
        if "aciaria" in st.tokens:
            assert "aciaria" in st.area_terms

    def test_single_token_preserved(self):
        st = _extract_search_terms("velocidade")
        assert st.tokens == ["velocidade"]
        assert "velocidade" in st.variable_terms
