"""
Integration tests for pi_request — requires PI Web API reachable.

Gated with pytest.mark.integration; skipped if connection fails.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp_server"))

from clients.pi_web_api_client import pi_request, get_data_server

PI_REACHABLE = True


def _check_pi():
    global PI_REACHABLE
    try:
        import httpx
        resp = httpx.get("http://10.247.224.39/piwebapi", timeout=5)
        PI_REACHABLE = resp.status_code < 500
    except Exception:
        PI_REACHABLE = False


_check_pi()

pytestmark = pytest.mark.skipif(
    not PI_REACHABLE,
    reason="PI Web API not reachable at http://10.247.224.39/piwebapi",
)


# ---------------------------------------------------------------------------
# /dataservers — list servers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_dataservers():
    result = await pi_request("GET", "/dataservers")
    assert result["ok"] is True
    assert "Items" in result["data"]
    names = [item.get("Name") for item in result["data"]["Items"]]
    assert "pims" in [n.lower() for n in names]


# ---------------------------------------------------------------------------
# PIMS WebId resolution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pims_webid_resolves():
    ds = await get_data_server()
    web_id = ds.get("WebId")
    assert web_id, "PIMS DataServer should have a WebId"


# ---------------------------------------------------------------------------
# /dataservers/{WebId}/points — search by descriptorFilter
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_by_descriptor():
    ds = await get_data_server()
    ds_webid = ds["WebId"]

    result = await pi_request(
        "GET",
        "/dataservers/{WebId}/points",
        path_params={"WebId": ds_webid},
        query_params={"descriptorFilter": "*pressao*", "maxCount": 10},
    )

    assert result["ok"] is True
    assert isinstance(result["Items"], list)
    assert result["items_count"] >= 0


# ---------------------------------------------------------------------------
# /points?path=... — get known point
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_point_by_path():
    result = await pi_request(
        "GET",
        "/points",
        query_params={
            "path": r"\\PIMS\LFI_RB3_VAZ_GN_TOTAL",
            "selectedFields": "WebId;Name;Descriptor;PointType;EngineeringUnits",
        },
    )

    assert result["ok"] is True
    assert result["data"].get("Name") == "LFI_RB3_VAZ_GN_TOTAL"


# ---------------------------------------------------------------------------
# /points/{WebId}/attributes — get attribute
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_attribute():
    point_result = await pi_request(
        "GET",
        "/points",
        query_params={"path": r"\\PIMS\LFI_RB3_VAZ_GN_TOTAL"},
    )
    assert point_result["ok"]
    web_id = point_result["data"]["WebId"]

    attr_result = await pi_request(
        "GET",
        "/points/{WebId}/attributes",
        path_params={"WebId": web_id},
        query_params={"name": "instrumenttag"},
    )

    assert attr_result["ok"] is True
    assert "data" in attr_result


# ---------------------------------------------------------------------------
# /streams/{WebId}/value — current value
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_current_value():
    point_result = await pi_request(
        "GET",
        "/points",
        query_params={"path": r"\\PIMS\LFI_RB3_VAZ_GN_TOTAL"},
    )
    assert point_result["ok"]
    web_id = point_result["data"]["WebId"]

    value_result = await pi_request(
        "GET",
        "/streams/{WebId}/value",
        path_params={"WebId": web_id},
    )

    assert value_result["ok"] is True
    assert "Value" in value_result["data"] or "value" in str(value_result["data"]).lower()
