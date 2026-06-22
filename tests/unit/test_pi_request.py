"""
Unit tests for pi_request in mcp_server/clients/pi_web_api_client.py.

Tests:
- Whitelist enforcement
- Method validation
- Path placeholder resolution
- List truncation
- Error propagation
- POST /batch
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp_server"))

from clients.pi_web_api_client import (
    ALLOWED_PI_ENDPOINTS,
    MAX_SEARCH_ITEMS,
    _resolve_placeholders,
    _format_search_items,
    pi_request,
)


# ---------------------------------------------------------------------------
# ALLOWED_PI_ENDPOINTS sanity checks
# ---------------------------------------------------------------------------
class TestWhitelist:
    def test_all_templates_have_required_keys(self):
        for path, meta in ALLOWED_PI_ENDPOINTS.items():
            assert "method" in meta, f"{path} missing 'method'"
            assert "description" in meta, f"{path} missing 'description'"
            assert "placeholders" in meta, f"{path} missing 'placeholders'"

    def test_no_template_starts_with_double_brace(self):
        for path in ALLOWED_PI_ENDPOINTS:
            assert "{{" not in path, f"{path} has double-brace placeholders"

    def test_expected_templates_present(self):
        expected = {
            "/points",
            "/points/{WebId}",
            "/points/{WebId}/attributes",
            "/streams/{WebId}/value",
            "/streams/{WebId}/recorded",
            "/streams/{WebId}/interpolated",
            "/streams/{WebId}/summary",
            "/streams/{WebId}/plot",
            "/dataservers",
            "/dataservers/{WebId}/points",
            "/dataservers/{WebId}/enumerationsets",
            "/enumerationsets/{WebId}/enumerationvalues",
            "/streamsets/value",
            "/streamsets/recorded",
            "/streamsets/interpolated",
            "/batch",
        }
        assert expected == set(ALLOWED_PI_ENDPOINTS.keys())


# ---------------------------------------------------------------------------
# _resolve_placeholders
# ---------------------------------------------------------------------------
class TestResolvePlaceholders:
    def test_no_placeholders(self):
        result = _resolve_placeholders("/points", {}, "GET")
        assert result == "/points"

    def test_webid_resolved(self):
        result = _resolve_placeholders(
            "/points/{WebId}",
            {"WebId": "P0DPmABC123"},
            "GET",
        )
        assert result == "/points/P0DPmABC123"

    def test_multiple_placeholders(self):
        result = _resolve_placeholders(
            "/dataservers/{WebId}/points",
            {"WebId": "DS_WEBID_42"},
            "GET",
        )
        assert result == "/dataservers/DS_WEBID_42/points"

    def test_missing_placeholder_raises(self):
        with pytest.raises(ValueError, match="exige o path_param"):
            _resolve_placeholders("/points/{WebId}", {}, "GET")

    def test_pims_placeholder_auto_filled(self):
        import clients.pi_web_api_client as mod

        mod.PIMS_DATASERVER_WEBID = "PIMS_AUTO_99"
        try:
            result = _resolve_placeholders(
                "/dataservers/{WebId}/points",
                {},
                "GET",
            )
            assert result == "/dataservers/PIMS_AUTO_99/points"
        finally:
            mod.PIMS_DATASERVER_WEBID = None


# ---------------------------------------------------------------------------
# _format_search_items
# ---------------------------------------------------------------------------
class TestFormatSearchItems:
    def test_empty_items(self):
        result = _format_search_items({"Items": []})
        assert result["ok"] is True
        assert result["items_count"] == 0
        assert result["truncated"] is False
        assert result["Items"] == []

    def test_under_limit(self):
        items = [{"Name": f"TAG_{i}", "WebId": f"W{i}", "Descriptor": f"Desc {i}"}
                 for i in range(5)]
        result = _format_search_items({"Items": items})
        assert result["items_count"] == 5
        assert result["truncated"] is False
        assert len(result["Items"]) == 5

    def test_at_limit(self):
        items = [{"Name": f"TAG_{i}"} for i in range(MAX_SEARCH_ITEMS)]
        result = _format_search_items({"Items": items})
        assert result["truncated"] is False
        assert len(result["Items"]) == MAX_SEARCH_ITEMS

    def test_over_limit_truncates(self):
        total = MAX_SEARCH_ITEMS + 5
        items = [{"Name": f"TAG_{i}", "WebId": f"W{i}", "Descriptor": f"Desc {i}",
                  "PointType": "Float32", "EngineeringUnits": "Nm3/h"}
                 for i in range(total)]
        result = _format_search_items({"Items": items})
        assert result["items_count"] == total
        assert result["truncated"] is True
        assert "hint" in result
        assert len(result["Items"]) == MAX_SEARCH_ITEMS

    def test_summary_fields_selected(self):
        raw = {"Items": [{"Name": "TAG_A", "WebId": "WA", "Descriptor": "Desc A",
                           "PointType": "Float32", "EngineeringUnits": "bar",
                           "ExtraField": "should_not_appear"}]}
        result = _format_search_items(raw)
        item = result["Items"][0]
        assert set(item.keys()) == {"Name", "WebId", "Descriptor", "PointType", "EngineeringUnits"}


# ---------------------------------------------------------------------------
# pi_request — validation
# ---------------------------------------------------------------------------
class TestPiRequestValidation:
    @pytest.mark.asyncio
    async def test_invalid_method(self):
        result = await pi_request("DELETE", "/points")
        assert result["ok"] is False
        assert "DELETE" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_path(self):
        result = await pi_request("GET", "/etc/passwd")
        assert result["ok"] is False
        assert "whitelist" in result["error"].lower() or "permitidos" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_method_mismatch(self):
        result = await pi_request("POST", "/points")
        assert result["ok"] is False
        assert "GET" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_method_string(self):
        result = await pi_request("put", "/points")
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# pi_request — successful GET (non-search)
# ---------------------------------------------------------------------------
class TestPiRequestGetSuccess:
    @pytest.mark.asyncio
    @patch("clients.pi_web_api_client._pi_get", new_callable=AsyncMock)
    async def test_get_points_by_path(self, mock_get):
        mock_get.return_value = {"WebId": "W123", "Name": "TAG1"}

        result = await pi_request(
            "GET",
            "/points",
            query_params={"path": r"\\PIMS\TAG1"},
        )

        assert result["ok"] is True
        assert result["data"]["WebId"] == "W123"
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch("clients.pi_web_api_client._pi_get", new_callable=AsyncMock)
    async def test_get_stream_value(self, mock_get):
        mock_get.return_value = {"Value": 42.5, "Timestamp": "2026-06-18T12:00:00Z"}

        result = await pi_request(
            "GET",
            "/streams/{WebId}/value",
            path_params={"WebId": "W123"},
        )

        assert result["ok"] is True
        assert result["data"]["Value"] == 42.5


# ---------------------------------------------------------------------------
# pi_request — search truncation
# ---------------------------------------------------------------------------
class TestPiRequestSearch:
    @pytest.mark.asyncio
    @patch("clients.pi_web_api_client._pi_get", new_callable=AsyncMock)
    async def test_search_returns_truncated(self, mock_get):
        items = [{"Name": f"TAG_{i}", "WebId": f"W{i}", "Descriptor": f"Desc {i}"}
                 for i in range(15)]
        mock_get.return_value = {"Items": items}

        result = await pi_request(
            "GET",
            "/dataservers/{WebId}/points",
            path_params={"WebId": "DS1"},
            query_params={"descriptorFilter": "*tag*", "maxCount": 10},
        )

        assert result["ok"] is True
        assert result["truncated"] is True
        assert result["items_count"] == 15
        assert len(result["Items"]) == MAX_SEARCH_ITEMS


# ---------------------------------------------------------------------------
# pi_request — POST /batch
# ---------------------------------------------------------------------------
class TestPiRequestBatch:
    @pytest.mark.asyncio
    @patch("clients.pi_web_api_client._pi_post", new_callable=AsyncMock)
    async def test_batch_post(self, mock_post):
        batch_response = {
            "point_0": {"Status": 200, "Content": {"Name": "TAG1"}},
            "value_0": {"Status": 200, "Content": {"Value": 10.0}},
        }
        mock_post.return_value = batch_response

        result = await pi_request(
            "POST",
            "/batch",
            json_body={
                "point_0": {
                    "Method": "GET",
                    "Resource": "http://10.247.224.39/piwebapi/points?path=\\\\PIMS\\TAG1",
                },
                "value_0": {
                    "Method": "GET",
                    "ParentIds": ["point_0"],
                    "Parameters": ["$.point_0.Content.WebId"],
                    "Resource": "http://10.247.224.39/piwebapi/streams/{0}/value",
                },
            },
        )

        assert result["ok"] is True
        assert "point_0" in result["data"]
        mock_post.assert_called_once()


# ---------------------------------------------------------------------------
# pi_request — HTTP error propagation
# ---------------------------------------------------------------------------
class TestPiRequestErrors:
    @pytest.mark.asyncio
    @patch("clients.pi_web_api_client._pi_get", new_callable=AsyncMock)
    async def test_http_404(self, mock_get):
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"Errors": ["Not Found"]}
        http_err = httpx.HTTPStatusError(
            "Not Found",
            request=AsyncMock(),
            response=mock_response,
        )
        mock_get.side_effect = http_err

        result = await pi_request(
            "GET",
            "/points",
            query_params={"path": r"\\PIMS\\NONEXISTENT"},
        )

        assert result["ok"] is False
        assert result["status_code"] == 404

    @pytest.mark.asyncio
    @patch("clients.pi_web_api_client._pi_get", new_callable=AsyncMock)
    async def test_generic_exception(self, mock_get):
        mock_get.side_effect = ConnectionError("refused")

        result = await pi_request(
            "GET",
            "/points",
            query_params={"path": r"\\PIMS\\TAG1"},
        )

        assert result["ok"] is False
        assert "refused" in result["error"]
