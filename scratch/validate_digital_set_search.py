import asyncio
import json
import httpx

from domain.core.config import configure_domain_settings
from app.core.config import settings
configure_domain_settings(settings.to_domain_integration_settings())
from domain.pims.clients.pi_web_api_client import get_data_server, _base_url, _pi_get

async def run_validation():
    results = {}
    
    # 0. Get DataServer WebId
    ds = await get_data_server()
    data_server_web_id = ds["WebId"]
    results["data_server_name"] = ds.get("Name")
    results["data_server_web_id"] = data_server_web_id
    
    # Get system info / version if available
    try:
        sys_info = await _pi_get(f"{_base_url()}/system/status")
        results["pi_web_api_version"] = sys_info.get("Version")
    except Exception as e:
        results["pi_web_api_version"] = f"Unknown ({e})"

    # Find a real digital tag and its DigitalSet
    print("--- Finding candidate digital tags ---")
    find_params = {
        "dataServerWebId": data_server_web_id,
        "query": "PointType:=Digital",
        "maxCount": 5,
        "selectedFields": "Items.WebId;Items.Name;Items.Path;Items.Descriptor;Items.PointType;Items.DigitalSetName",
    }
    raw_find = await _pi_get(f"{_base_url()}/points/search", params=find_params)
    items_find = raw_find.get("Items", [])
    print(f"Found {len(items_find)} digital points")
    
    digital_set_known = None
    sample_tag = None
    for item in items_find:
        print("Item sample:", item)
        dset = item.get("DigitalSetName") or item.get("DigitalSet") or item.get("digitalset")
        if dset:
            digital_set_known = dset
            sample_tag = item.get("Name")
            break

    # If selectedFields omitted DigitalSetName, let's query full object for 1 point
    if not digital_set_known and items_find:
        web_id_sample = items_find[0]["WebId"]
        point_full = await _pi_get(f"{_base_url()}/points/{web_id_sample}")
        print("Point full sample keys:", list(point_full.keys()))
        digital_set_known = point_full.get("DigitalSetName") or point_full.get("DigitalSet") or point_full.get("digitalset")
        sample_tag = point_full.get("Name")
        print(f"Full point digital set: {digital_set_known}")

    if not digital_set_known:
        results["error"] = "No digital set found in candidate tags"
        print(json.dumps(results, indent=2))
        return

    results["known_digital_set"] = digital_set_known
    results["sample_tag"] = sample_tag

    # -------------------------------------------------------------
    # V1 — Digital Set conhecido
    # -------------------------------------------------------------
    print(f"\n--- V1: Querying known DigitalSet '{digital_set_known}' ---")
    v1_params = {
        "dataServerWebId": data_server_web_id,
        "query": f'PointType:=Digital AND DigitalSet:="{digital_set_known}"',
        "startIndex": 0,
        "maxCount": 2,
        "selectedFields": "Items.WebId;Items.Name;Items.Path;Items.Descriptor;Items.PointType;Items.DigitalSetName",
    }
    try:
        v1_raw = await _pi_get(f"{_base_url()}/points/search", params=v1_params)
        v1_items = v1_raw.get("Items", [])
        results["V1"] = {
            "http_status": 200,
            "query_used": v1_params["query"],
            "count": len(v1_items),
            "returned_fields": list(v1_items[0].keys()) if v1_items else [],
            "items_sample": v1_items,
        }
    except httpx.HTTPStatusError as exc:
        results["V1"] = {
            "http_status": exc.response.status_code,
            "error_body": exc.response.text[:300],
        }
    except Exception as exc:
        results["V1"] = {"error": str(exc)}

    # -------------------------------------------------------------
    # V2 — Digital Set inexistente
    # -------------------------------------------------------------
    print("\n--- V2: Querying non-existent DigitalSet ---")
    v2_params = {
        "dataServerWebId": data_server_web_id,
        "query": 'PointType:=Digital AND DigitalSet:="__DIGITAL_SET_INEXISTENTE_VALIDACAO__"',
        "startIndex": 0,
        "maxCount": 2,
        "selectedFields": "Items.WebId;Items.Name;Items.Path;Items.Descriptor;Items.PointType;Items.DigitalSetName",
    }
    try:
        v2_raw = await _pi_get(f"{_base_url()}/points/search", params=v2_params)
        v2_items = v2_raw.get("Items", [])
        results["V2"] = {
            "http_status": 200,
            "query_used": v2_params["query"],
            "count": len(v2_items),
            "filter_applied": len(v2_items) == 0,
        }
    except httpx.HTTPStatusError as exc:
        results["V2"] = {
            "http_status": exc.response.status_code,
            "error_body": exc.response.text[:300],
        }
    except Exception as exc:
        results["V2"] = {"error": str(exc)}

    # -------------------------------------------------------------
    # V3 — Sensibilidade à caixa
    # -------------------------------------------------------------
    print("\n--- V3: Case sensitivity test ---")
    dset_cased = digital_set_known.lower() if digital_set_known != digital_set_known.lower() else digital_set_known.upper()
    v3_params = {
        "dataServerWebId": data_server_web_id,
        "query": f'PointType:=Digital AND DigitalSet:="{dset_cased}"',
        "startIndex": 0,
        "maxCount": 2,
        "selectedFields": "Items.WebId;Items.Name;Items.Path;Items.Descriptor;Items.PointType;Items.DigitalSetName",
    }
    try:
        v3_raw = await _pi_get(f"{_base_url()}/points/search", params=v3_params)
        v3_items = v3_raw.get("Items", [])
        results["V3"] = {
            "http_status": 200,
            "original_case": digital_set_known,
            "tested_case": dset_cased,
            "count": len(v3_items),
            "classification": "case-insensitive" if len(v3_items) == len(results.get("V1", {}).get("items_sample", [])) else "case-sensitive",
        }
    except Exception as exc:
        results["V3"] = {"error": str(exc)}

    # -------------------------------------------------------------
    # V4 — Paginação
    # -------------------------------------------------------------
    print("\n--- V4: Pagination test ---")
    v4_p0 = {
        "dataServerWebId": data_server_web_id,
        "query": f'PointType:=Digital AND DigitalSet:="{digital_set_known}"',
        "startIndex": 0,
        "maxCount": 1,
        "selectedFields": "Items.WebId;Items.Name;Items.Path;Items.Descriptor;Items.PointType;Items.DigitalSetName",
    }
    v4_p1 = dict(v4_p0, startIndex=1)
    try:
        r0 = await _pi_get(f"{_base_url()}/points/search", params=v4_p0)
        r1 = await _pi_get(f"{_base_url()}/points/search", params=v4_p1)
        i0 = r0.get("Items", [])
        i1 = r1.get("Items", [])
        name0 = i0[0]["Name"] if i0 else None
        name1 = i1[0]["Name"] if i1 else None
        results["V4"] = {
            "page0_item": name0,
            "page1_item": name1,
            "pagination_working": (name0 != name1) if (name0 and name1) else "insufficient_items_to_test",
        }
    except Exception as exc:
        results["V4"] = {"error": str(exc)}

    # -------------------------------------------------------------
    # V5 — Campo do Digital Set (sem selectedFields)
    # -------------------------------------------------------------
    print("\n--- V5: Full item field check ---")
    v5_params = {
        "dataServerWebId": data_server_web_id,
        "query": f'PointType:=Digital AND DigitalSet:="{digital_set_known}"',
        "startIndex": 0,
        "maxCount": 1,
    }
    try:
        v5_raw = await _pi_get(f"{_base_url()}/points/search", params=v5_params)
        v5_items = v5_raw.get("Items", [])
        if v5_items:
            item_full = v5_items[0]
            matched_field = None
            for f in ["DigitalSetName", "DigitalSet", "digitalset"]:
                if f in item_full and item_full[f]:
                    matched_field = f
                    break
            results["V5"] = {
                "matched_field": matched_field,
                "all_keys": list(item_full.keys()),
                "digital_set_value": item_full.get(matched_field) if matched_field else None,
            }
        else:
            results["V5"] = {"matched_field": None, "count": 0}
    except Exception as exc:
        results["V5"] = {"error": str(exc)}

    print("\n================ FINAL RESULTS ================")
    print(json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(run_validation())
