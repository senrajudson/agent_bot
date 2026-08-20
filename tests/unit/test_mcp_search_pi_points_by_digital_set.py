import json
import pytest
from unittest.mock import patch, AsyncMock

from mcp_server.server import mcp, search_pi_points_by_digital_set


@pytest.mark.asyncio
async def test_mcp_search_pi_points_by_digital_set_registered():
    tools = await mcp.get_tools()
    assert "search_pi_points_by_digital_set" in tools


@pytest.mark.asyncio
async def test_mcp_search_pi_points_by_digital_set_delegation():
    fake_service_result = {
        "status": "success",
        "digital_set_name": "Estado_01",
        "returned_count": 1,
        "start_index": 0,
        "next_start_index": None,
        "truncated": False,
        "items": [
            {
                "name": "TAG_1",
                "description": "Desc 1",
                "point_type": "Digital",
                "digital_set_name": "Estado_01",
                "path": "\\\\pims\\TAG_1",
                "web_id": "WEBID_1",
            }
        ],
        "output": '{"status": "success", "digital_set_name": "Estado_01", "returned_count": 1, "start_index": 0, "next_start_index": null, "truncated": false, "items": [{"name": "TAG_1", "description": "Desc 1", "point_type": "Digital", "digital_set_name": "Estado_01", "path": "\\\\\\\\pims\\\\\\\\TAG_1", "web_id": "WEBID_1"}]}',
    }

    with patch("domain.pims.services.search_points_by_digital_set_service.search_pi_points_by_digital_set", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = fake_service_result

        result = await search_pi_points_by_digital_set.fn("Estado_01", max_count=100, start_index=0)

        mock_svc.assert_called_once_with(
            digital_set_name="Estado_01",
            max_count=100,
            start_index=0,
        )
        # _mcp_safe_tool parses JSON output strings into dicts for safety checks
        assert isinstance(result, (dict, str))
        if isinstance(result, dict):
            assert result["status"] == "success"
            assert result["digital_set_name"] == "Estado_01"
            assert len(result["items"]) == 1
