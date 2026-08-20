import pytest
from unittest.mock import patch, AsyncMock

from domain.pims.clients.pi_web_api_client import search_points_by_digital_set


@pytest.mark.asyncio
async def test_search_points_by_digital_set_success():
    fake_data_server = {"WebId": "FAKE_SERVER_WEBID", "Name": "pims"}
    fake_api_response = {
        "Items": [
            {
                "WebId": "WEBID_1",
                "Name": "TAG_DIGITAL_1",
                "Path": "\\\\pims\\TAG_DIGITAL_1",
                "Descriptor": "Desc 1",
                "PointType": "Digital",
                "DigitalSetName": "Estado_01",
            }
        ]
    }

    with patch("domain.pims.clients.pi_web_api_client.get_data_server", new_callable=AsyncMock) as mock_ds, \
         patch("domain.pims.clients.pi_web_api_client._pi_get", new_callable=AsyncMock) as mock_get:
        mock_ds.return_value = fake_data_server
        mock_get.return_value = fake_api_response

        result = await search_points_by_digital_set("Estado_01", max_count=100, start_index=0)

        mock_ds.assert_called_once()
        mock_get.assert_called_once()

        url_arg, = mock_get.call_args.args
        params_kw = mock_get.call_args.kwargs.get("params", {})

        assert url_arg.endswith("/points/search")
        assert params_kw["dataServerWebId"] == "FAKE_SERVER_WEBID"
        assert params_kw["query"] == 'PointType:=Digital AND DigitalSet:="Estado_01"'
        assert params_kw["startIndex"] == 0
        assert params_kw["maxCount"] == 100
        assert "Items.DigitalSetName" in params_kw["selectedFields"]

        assert result == fake_api_response
