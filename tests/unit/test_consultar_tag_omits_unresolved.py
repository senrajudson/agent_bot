from unittest.mock import AsyncMock, patch

import pytest

from domain.pims.services.consultar_tag_service import consultar_tags_pi


@pytest.mark.asyncio
async def test_no_unresolved():
    raw_response = {
        "point_0": {"Status": 200, "Content": {"Name": "T1", "WebId": "A1"}},
        "point_1": {"Status": 200, "Content": {"Name": "T2", "WebId": "A2"}},
    }
    with patch(
        "domain.pims.services.consultar_tag_service.get_tags_data",
        new_callable=AsyncMock,
        return_value=raw_response,
    ), patch(
        "domain.pims.services.consultar_tag_service.enriquecer_com_digital_states",
        new_callable=AsyncMock,
        return_value={
            "resultados_pi": [
                {"nome": "T1", "pointType": "Float32"},
                {"nome": "T2", "pointType": "Float32"},
            ],
            "tem_tag_digital": False,
            "qtd_tags_digitais": 0,
            "qtd_digital_sets": 0,
            "digital_sets_consultados": [],
            "digital_states_por_set": {},
        },
    ):
        result = await consultar_tags_pi(["T1", "T2"])
    assert result["ok"] is True
    assert "tags_nao_resolvidas" not in result["tool_result"]
    assert len(result["tool_result"]["resultados_pi"]) == 2


@pytest.mark.asyncio
async def test_one_unresolved():
    raw_response = {
        "point_0": {"Status": 200, "Content": {"Name": "T1", "WebId": "A1"}},
        "point_1": {"Status": 404, "Content": {}},
    }
    with patch(
        "domain.pims.services.consultar_tag_service.get_tags_data",
        new_callable=AsyncMock,
        return_value=raw_response,
    ), patch(
        "domain.pims.services.consultar_tag_service.enriquecer_com_digital_states",
        new_callable=AsyncMock,
        return_value={
            "resultados_pi": [
                {"nome": "T1", "pointType": "Float32"},
            ],
            "tem_tag_digital": False,
            "qtd_tags_digitais": 0,
            "qtd_digital_sets": 0,
            "digital_sets_consultados": [],
            "digital_states_por_set": {},
        },
    ):
        result = await consultar_tags_pi(["T1", "T2"])
    assert result["ok"] is True
    assert result["tool_result"]["tags_nao_resolvidas"] == ["T2"]
    assert len(result["tool_result"]["resultados_pi"]) == 1


@pytest.mark.asyncio
async def test_multiple_unresolved():
    raw_response = {
        "point_0": {"Status": 500, "Content": {}},
        "point_1": {"Status": 200, "Content": {"Name": "T2", "WebId": "A2"}},
        "point_2": {"Status": 404, "Content": {}},
    }
    with patch(
        "domain.pims.services.consultar_tag_service.get_tags_data",
        new_callable=AsyncMock,
        return_value=raw_response,
    ), patch(
        "domain.pims.services.consultar_tag_service.enriquecer_com_digital_states",
        new_callable=AsyncMock,
        return_value={
            "resultados_pi": [
                {"nome": "T2", "pointType": "Float32"},
            ],
            "tem_tag_digital": False,
            "qtd_tags_digitais": 0,
            "qtd_digital_sets": 0,
            "digital_sets_consultados": [],
            "digital_states_por_set": {},
        },
    ):
        result = await consultar_tags_pi(["T1", "T2", "T3"])
    assert result["ok"] is True
    assert sorted(result["tool_result"]["tags_nao_resolvidas"]) == ["T1", "T3"]
    assert len(result["tool_result"]["resultados_pi"]) == 1


@pytest.mark.asyncio
async def test_all_unresolved():
    raw_response = {
        "point_0": {"Status": 404, "Content": {}},
        "point_1": {"Status": 500, "Content": {}},
    }
    with patch(
        "domain.pims.services.consultar_tag_service.get_tags_data",
        new_callable=AsyncMock,
        return_value=raw_response,
    ), patch(
        "domain.pims.services.consultar_tag_service.enriquecer_com_digital_states",
        new_callable=AsyncMock,
        return_value={
            "resultados_pi": [],
            "tem_tag_digital": False,
            "qtd_tags_digitais": 0,
            "qtd_digital_sets": 0,
            "digital_sets_consultados": [],
            "digital_states_por_set": {},
        },
    ):
        result = await consultar_tags_pi(["T1", "T2"])
    assert result["ok"] is True
    assert sorted(result["tool_result"]["tags_nao_resolvidas"]) == ["T1", "T2"]
    assert len(result["tool_result"]["resultados_pi"]) == 0
