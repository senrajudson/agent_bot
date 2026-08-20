import pytest
from unittest.mock import patch, AsyncMock
import httpx

from domain.pims.services.search_points_by_digital_set_service import (
    search_pi_points_by_digital_set,
)


@pytest.mark.asyncio
async def test_validation_invalid_digital_set_name():
    # Empty string
    res = await search_pi_points_by_digital_set("")
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_digital_set_name"

    # Whitespace only
    res = await search_pi_points_by_digital_set("   ")
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_digital_set_name"

    # Metacharacters: wildcard *
    res = await search_pi_points_by_digital_set("Estado_*")
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_digital_set_name"

    # Quotes
    res = await search_pi_points_by_digital_set('Estado_"01"')
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_digital_set_name"

    # Backslash
    res = await search_pi_points_by_digital_set("Estado_\\01")
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_digital_set_name"


@pytest.mark.asyncio
async def test_validation_invalid_limits():
    # max_count < 1
    res = await search_pi_points_by_digital_set("Estado_01", max_count=0)
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_max_count"

    # max_count > 1000
    res = await search_pi_points_by_digital_set("Estado_01", max_count=1001)
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_max_count"

    # start_index < 0
    res = await search_pi_points_by_digital_set("Estado_01", start_index=-1)
    assert res["status"] == "error"
    assert res["error"]["code"] == "invalid_start_index"


@pytest.mark.asyncio
async def test_success_field_precedence_and_defensive_filtering():
    fake_items = [
        # Item 1: DigitalSetName present, valid
        {
            "Name": "TAG_1",
            "Descriptor": "Desc 1",
            "PointType": "Digital",
            "DigitalSetName": "Estado_01",
            "Path": "\\\\pims\\TAG_1",
            "WebId": "WEBID_1",
        },
        # Item 2: DigitalSet present (fallback 1), valid with case variation
        {
            "Name": "TAG_2",
            "Descriptor": "Desc 2",
            "PointType": "digital",
            "DigitalSet": "ESTADO_01",
            "Path": "\\\\pims\\TAG_2",
            "WebId": "WEBID_2",
        },
        # Item 3: digitalset present (fallback 2), valid
        {
            "Name": "TAG_3",
            "Descriptor": "Desc 3",
            "PointType": "Digital",
            "digitalset": "estado_01",
            "Path": "\\\\pims\\TAG_3",
            "WebId": "WEBID_3",
        },
        # Item 4: Different DigitalSet (defensive filter should reject)
        {
            "Name": "TAG_4",
            "Descriptor": "Desc 4",
            "PointType": "Digital",
            "DigitalSetName": "Estado_02",
            "Path": "\\\\pims\\TAG_4",
            "WebId": "WEBID_4",
        },
        # Item 5: Non-digital point (defensive filter should reject)
        {
            "Name": "TAG_5",
            "Descriptor": "Desc 5",
            "PointType": "Float32",
            "DigitalSetName": "Estado_01",
            "Path": "\\\\pims\\TAG_5",
            "WebId": "WEBID_5",
        },
    ]

    with patch("domain.pims.services.search_points_by_digital_set_service.client_search", new_callable=AsyncMock) as mock_client:
        mock_client.return_value = {"Items": fake_items}

        res = await search_pi_points_by_digital_set("  Estado_01  ", max_count=10, start_index=0)

        assert res["status"] == "success"
        assert res["digital_set_name"] == "Estado_01"
        assert res["returned_count"] == 3
        assert res["start_index"] == 0
        assert res["next_start_index"] is None
        assert res["truncated"] is False
        assert len(res["items"]) == 3
        assert res["items"][0]["name"] == "TAG_1"
        assert res["items"][1]["name"] == "TAG_2"
        assert res["items"][2]["name"] == "TAG_3"


@pytest.mark.asyncio
async def test_pagination_and_truncation():
    # Simulate 2 raw items returned when max_count=2 (page full -> truncated=True)
    fake_items = [
        {
            "Name": "TAG_1",
            "Descriptor": "Desc 1",
            "PointType": "Digital",
            "DigitalSetName": "Estado_01",
            "Path": "\\\\pims\\TAG_1",
            "WebId": "WEBID_1",
        },
        {
            "Name": "TAG_2",
            "Descriptor": "Desc 2",
            "PointType": "Digital",
            "DigitalSetName": "Estado_01",
            "Path": "\\\\pims\\TAG_2",
            "WebId": "WEBID_2",
        },
    ]

    with patch("domain.pims.services.search_points_by_digital_set_service.client_search", new_callable=AsyncMock) as mock_client:
        mock_client.return_value = {"Items": fake_items}

        res = await search_pi_points_by_digital_set("Estado_01", max_count=2, start_index=0)

        assert res["status"] == "success"
        assert res["returned_count"] == 2
        assert res["start_index"] == 0
        assert res["next_start_index"] == 2  # start_index (0) + raw_count (2)
        assert res["truncated"] is True


@pytest.mark.asyncio
async def test_no_data_response():
    with patch("domain.pims.services.search_points_by_digital_set_service.client_search", new_callable=AsyncMock) as mock_client:
        mock_client.return_value = {"Items": []}

        res = await search_pi_points_by_digital_set("Estado_01", max_count=100, start_index=0)

        assert res["status"] == "no_data"
        assert res["digital_set_name"] == "Estado_01"
        assert res["returned_count"] == 0
        assert res["start_index"] == 0
        assert res["next_start_index"] is None
        assert res["truncated"] is False
        assert res["items"] == []


@pytest.mark.asyncio
async def test_http_error_handling():
    with patch("domain.pims.services.search_points_by_digital_set_service.client_search", new_callable=AsyncMock) as mock_client:
        mock_req = httpx.Request("GET", "http://test/points/search")
        mock_resp = httpx.Response(400, text="Bad Request", request=mock_req)
        mock_client.side_effect = httpx.HTTPStatusError("HTTP 400", request=mock_req, response=mock_resp)

        res = await search_pi_points_by_digital_set("Estado_01")

        assert res["status"] == "error"
        assert res["error"]["code"] == "pi_web_api_query_unsupported"
        assert res["error"]["http_status"] == 400
