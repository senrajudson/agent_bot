from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

import httpx

from core.config import settings


_DATASERVER_CACHE: dict[str, Any] = {}
_ENUM_SET_CACHE: dict[str, dict[str, Any]] = {}

TemporalDataMethod = Literal["recorded", "interpolated", "summary"]

POINT_SELECTED_FIELDS = (
    "WebId;Name;Descriptor;EngineeringUnits;PointType;DigitalSet"
)

MAX_SEARCH_ITEMS = 10

ALLOWED_PI_ENDPOINTS: dict[str, dict[str, Any]] = {
    "/points": {
        "method": "GET",
        "description": "Get PI Point by path or list points root",
        "placeholders": [],
    },
    "/points/{WebId}": {
        "method": "GET",
        "description": "Get PI Point by WebId",
        "placeholders": ["WebId"],
    },
    "/points/{WebId}/attributes": {
        "method": "GET",
        "description": "Get attributes (instrumenttag, location1..5, engunits, etc.)",
        "placeholders": ["WebId"],
    },
    "/streams/{WebId}/value": {
        "method": "GET",
        "description": "Current value of a tag",
        "placeholders": ["WebId"],
    },
    "/streams/{WebId}/recorded": {
        "method": "GET",
        "description": "Raw recorded history",
        "placeholders": ["WebId"],
    },
    "/streams/{WebId}/interpolated": {
        "method": "GET",
        "description": "Fixed-interval interpolated values",
        "placeholders": ["WebId"],
    },
    "/streams/{WebId}/summary": {
        "method": "GET",
        "description": "Aggregations (Average, Max, Min, Total, Count, etc.)",
        "placeholders": ["WebId"],
    },
    "/streams/{WebId}/plot": {
        "method": "GET",
        "description": "Plot data for a tag",
        "placeholders": ["WebId"],
    },
    "/dataservers": {
        "method": "GET",
        "description": "List all data servers",
        "placeholders": [],
    },
    "/dataservers/{WebId}/points": {
        "method": "GET",
        "description": "Search/list points by nameFilter, descriptorFilter, or instrumenttagFilter",
        "placeholders": ["WebId"],
    },
    "/dataservers/{WebId}/enumerationsets": {
        "method": "GET",
        "description": "List enumeration sets for a data server",
        "placeholders": ["WebId"],
    },
    "/enumerationsets/{WebId}/enumerationvalues": {
        "method": "GET",
        "description": "Get digital states for an enumeration set",
        "placeholders": ["WebId"],
    },
    "/streamsets/value": {
        "method": "GET",
        "description": "Current value for multiple tags (use ?webId=...)",
        "placeholders": [],
    },
    "/streamsets/recorded": {
        "method": "GET",
        "description": "Recorded values for multiple tags",
        "placeholders": [],
    },
    "/streamsets/interpolated": {
        "method": "GET",
        "description": "Interpolated values for multiple tags",
        "placeholders": [],
    },
    "/batch": {
        "method": "POST",
        "description": "Multi-subrequest batch (point + value + attributes)",
        "placeholders": [],
    },
}

PIMS_DATASERVER_WEBID: str | None = None


async def _get_pims_dataserver_webid() -> str:
    global PIMS_DATASERVER_WEBID
    if PIMS_DATASERVER_WEBID:
        return PIMS_DATASERVER_WEBID
    ds = await get_data_server()
    wid = ds.get("WebId")
    if not wid:
        raise RuntimeError("PIMS Data Server has no WebId.")
    PIMS_DATASERVER_WEBID = wid
    return wid


def _resolve_placeholders(
    path_template: str,
    path_params: dict[str, str] | None,
    method: str,
) -> str:
    required = ALLOWED_PI_ENDPOINTS[path_template]["placeholders"]
    params = dict(path_params or {})

    if required and PIMS_DATASERVER_WEBID:
        for placeholder in required:
            if placeholder not in params or not params[placeholder]:
                params[placeholder] = PIMS_DATASERVER_WEBID

    for placeholder in required:
        value = params.get(placeholder)
        if not value:
            raise ValueError(
                f"O path_template '{path_template}' exige o path_param '{placeholder}'."
            )

    path = path_template
    all_params = dict(params)
    for key in required:
        if key in all_params:
            path = path.replace("{" + key + "}", all_params[key])

    return path


def _format_search_items(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("Items") or []
    total = len(items)
    truncated = total > MAX_SEARCH_ITEMS
    limited_items = items[:MAX_SEARCH_ITEMS]

    summary: list[dict[str, Any]] = []
    for item in limited_items:
        summary.append(
            {
                "Name": item.get("Name"),
                "WebId": item.get("WebId"),
                "Descriptor": item.get("Descriptor"),
                "PointType": item.get("PointType"),
                "EngineeringUnits": item.get("EngineeringUnits"),
            }
        )

    result: dict[str, Any] = {
        "ok": True,
        "items_count": total,
        "truncated": truncated,
    }

    if truncated:
        result["hint"] = (
            f"{total} resultados encontrados. "
            f"Retornando os primeiros {MAX_SEARCH_ITEMS}. "
            "Refine a busca com termos mais específicos."
        )

    result["Items"] = summary
    return result


async def pi_request(
    method: str,
    path_template: str,
    path_params: dict[str, str] | None = None,
    query_params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    method = (method or "").strip().upper()

    if method not in {"GET", "POST"}:
        allowed = list({ep["method"] for ep in ALLOWED_PI_ENDPOINTS.values()})
        return {
            "ok": False,
            "error": f"Method '{method}' não suportado. Métodos permitidos: {', '.join(sorted(allowed))}.",
        }

    if path_template not in ALLOWED_PI_ENDPOINTS:
        allowed = sorted(ALLOWED_PI_ENDPOINTS.keys())
        return {
            "ok": False,
            "error": (
                f"Path '{path_template}' não está na whitelist. "
                f"Templates permitidos:\n" + "\n".join(f"- {p}" for p in allowed)
            ),
        }

    ep_method = ALLOWED_PI_ENDPOINTS[path_template]["method"]

    if method != ep_method:
        return {
            "ok": False,
            "error": (
                f"Path '{path_template}' espera method '{ep_method}', "
                f"mas recebeu '{method}'."
            ),
        }

    if method == "GET":
        params = path_params or {}
        if path_template == "/dataservers/{WebId}/points" and "PIMS_DATASERVER_WEBID" in params:
            wid = await _get_pims_dataserver_webid()
            params["PIMS_DATASERVER_WEBID"] = wid

        resolved_path = _resolve_placeholders(path_template, params, method)
        full_url = f"{_base_url()}{resolved_path}"

        try:
            data = await _pi_get(full_url, params=query_params)
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "status_code": e.response.status_code,
                "path_called": resolved_path,
                "params_called": query_params,
                "error": f"PI Web API retornou HTTP {e.response.status_code}.",
            }
        except Exception as e:
            return {
                "ok": False,
                "path_called": resolved_path,
                "params_called": query_params,
                "error": f"Erro ao chamar PI Web API: {e}",
            }

        search_templates = {"/dataservers/{WebId}/points"}
        if path_template in search_templates:
            return _format_search_items(data)

        return {
            "ok": True,
            "path_called": resolved_path,
            "params_called": query_params,
            "data": data,
        }

    resolved_path = _resolve_placeholders(path_template, path_params, method)
    full_url = f"{_base_url()}{resolved_path}"

    try:
        data = await _pi_post(full_url, json_body=json_body or {})
    except httpx.HTTPStatusError as e:
        return {
            "ok": False,
            "status_code": e.response.status_code,
            "path_called": resolved_path,
            "error": f"PI Web API retornou HTTP {e.response.status_code}.",
        }
    except Exception as e:
        return {
            "ok": False,
            "path_called": resolved_path,
            "error": f"Erro ao chamar PI Web API: {e}",
        }

    return {
        "ok": True,
        "path_called": resolved_path,
        "data": data,
    }


def _get_auth() -> tuple[str, str] | None:
    if settings.PI_WEB_API_USERNAME and settings.PI_WEB_API_PASSWORD:
        return settings.PI_WEB_API_USERNAME, settings.PI_WEB_API_PASSWORD

    return None


def _base_url() -> str:
    return settings.PI_WEB_API_BASE_URL.rstrip("/")


def _normalize_pi_link(url: str) -> str:
    if not url:
        return url

    base_url = _base_url()
    parsed_base = urlparse(base_url)
    parsed_url = urlparse(url)

    if parsed_url.scheme and parsed_url.netloc:
        return urlunparse(
            (
                parsed_base.scheme,
                parsed_base.netloc,
                parsed_url.path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment,
            )
        )

    if url.startswith("/"):
        return f"{parsed_base.scheme}://{parsed_base.netloc}{url}"

    return url


async def _pi_get(
    url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=60,
        verify=settings.PI_WEB_API_VERIFY_SSL,
        auth=_get_auth(),
    ) as client:
        response = await client.get(
            _normalize_pi_link(url),
            params=params,
        )

    response.raise_for_status()
    return response.json()


async def _pi_post(
    url: str,
    json_body: dict[str, Any],
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=60,
        verify=settings.PI_WEB_API_VERIFY_SSL,
        auth=_get_auth(),
    ) as client:
        response = await client.post(
            _normalize_pi_link(url),
            json=json_body,
        )

    response.raise_for_status()
    return response.json()


def _pi_path(tag: str) -> str:
    tag_limpa = str(tag or "").strip()

    if not tag_limpa:
        raise ValueError("Tag vazia ou inválida.")

    return f"\\\\{settings.PI_SERVER_NAME}\\{tag_limpa}"


def _get_web_id(point: dict[str, Any]) -> str:
    web_id = point.get("WebId")

    if not web_id:
        raise ValueError("A resposta do PI Point não possui WebId.")

    return web_id


def _normalizar_metodo_temporal(method: str) -> str:
    method = str(method or "").strip().lower()

    if method not in {"recorded", "interpolated", "summary"}:
        raise ValueError(
            "Método temporal inválido. Use recorded, interpolated ou summary."
        )

    return method


async def _get_point_and_web_id(tag: str) -> tuple[dict[str, Any], str]:
    point = await get_point_by_tag(tag)
    return point, _get_web_id(point)


async def _get_stream_by_web_id(
    web_id: str,
    endpoint: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return await _pi_get(
        f"{_base_url()}/streams/{web_id}/{endpoint}",
        params=params,
    )


def build_tags_batch_request(tags: list[str]) -> dict[str, Any]:
    batch_request: dict[str, Any] = {}
    base_url = _base_url()

    for index, tag in enumerate(tags):
        pi_path = _pi_path(tag)

        batch_request[f"point_{index}"] = {
            "Method": "GET",
            "Resource": (
                f"{base_url}/points"
                f"?path={pi_path}"
                f"&selectedFields={POINT_SELECTED_FIELDS}"
            ),
        }

        batch_request[f"value_{index}"] = {
            "Method": "GET",
            "ParentIds": [f"point_{index}"],
            "Parameters": [f"$.point_{index}.Content.WebId"],
            "Resource": f"{base_url}/streams/{{0}}/value",
        }

        attributes = [
            "instrumenttag",
            "engunits",
            "pointtype",
            "digitalset",
            "location1",
            "location2",
            "location3",
            "location4",
            "location5",
        ]

        for attr in attributes:
            batch_request[f"{attr}_{index}"] = {
                "Method": "GET",
                "ParentIds": [f"point_{index}"],
                "Parameters": [f"$.point_{index}.Content.WebId"],
                "Resource": f"{base_url}/points/{{0}}/attributes?name={attr}",
            }

    return batch_request


async def execute_pi_batch(batch_request: dict[str, Any]) -> dict[str, Any]:
    return await _pi_post(
        url=f"{_base_url()}/batch",
        json_body=batch_request,
    )


async def get_tags_data(tags: list[str]) -> dict[str, Any]:
    return await execute_pi_batch(build_tags_batch_request(tags))


async def get_data_server() -> dict[str, Any]:
    cache_key = settings.PI_SERVER_NAME.upper()

    if cache_key in _DATASERVER_CACHE:
        return _DATASERVER_CACHE[cache_key]

    data = await _pi_get(f"{_base_url()}/dataservers")
    items = data.get("Items") or []

    if not items:
        raise RuntimeError("Nenhum Data Server foi retornado pela PI Web API.")

    server_name = settings.PI_SERVER_NAME.lower()

    for item in items:
        name = str(item.get("Name") or "").lower()

        if name == server_name:
            _DATASERVER_CACHE[cache_key] = item
            return item

    raise RuntimeError(f"Data Server {settings.PI_SERVER_NAME} não encontrado.")


async def get_enumeration_sets_url() -> str:
    data_server = await get_data_server()

    links = data_server.get("Links") or {}
    enumeration_sets_url = links.get("EnumerationSets")

    if enumeration_sets_url:
        return _normalize_pi_link(enumeration_sets_url)

    web_id = data_server.get("WebId")

    if not web_id:
        raise RuntimeError("Data Server não possui WebId nem link EnumerationSets.")

    return f"{_base_url()}/dataservers/{web_id}/enumerationsets"


async def get_all_enumeration_sets() -> list[dict[str, Any]]:
    data = await _pi_get(
        await get_enumeration_sets_url(),
        params={
            "selectedFields": "Items.WebId;Items.Name;Items.Description",
        },
    )

    return data.get("Items") or []


async def find_enumeration_set(digital_set: str) -> dict[str, Any] | None:
    digital_set_normalizado = str(digital_set or "").strip().lower()

    if not digital_set_normalizado:
        return None

    enum_sets = await get_all_enumeration_sets()

    for enum_set in enum_sets:
        name = str(enum_set.get("Name") or "").strip().lower()

        if name == digital_set_normalizado:
            return enum_set

    return None


async def get_enumeration_set_values(
    enum_set: dict[str, Any],
) -> list[dict[str, Any]]:
    web_id = enum_set.get("WebId")

    if not web_id:
        return []

    data = await _pi_get(
        f"{_base_url()}/enumerationsets/{web_id}/enumerationvalues",
        params={
            "selectedFields": "Items.Name;Items.Value;Items.Description",
        },
    )

    return data.get("Items") or []


async def get_digital_set_states(digital_set: str) -> dict[str, Any]:
    digital_set = str(digital_set or "").strip()

    if not digital_set:
        return {
            "digital_set": digital_set,
            "found": False,
            "states": [],
        }

    cache_key = digital_set.lower()

    if cache_key in _ENUM_SET_CACHE:
        return _ENUM_SET_CACHE[cache_key]

    enum_set = await find_enumeration_set(digital_set)

    if not enum_set:
        result = {
            "digital_set": digital_set,
            "found": False,
            "states": [],
        }
        _ENUM_SET_CACHE[cache_key] = result
        return result

    values = await get_enumeration_set_values(enum_set)

    states = []

    for item in values:
        nome_estado = item.get("Name")

        if nome_estado is None or str(nome_estado).strip() == "":
            nome_estado = "VAZIO"

        states.append(
            {
                "indice": item.get("Value"),
                "nome": nome_estado,
                "descricao": item.get("Description"),
            }
        )

    result = {
        "digital_set": enum_set.get("Name") or digital_set,
        "found": True,
        "states": states,
    }

    _ENUM_SET_CACHE[cache_key] = result
    return result


async def get_point_by_tag(tag: str) -> dict[str, Any]:
    return await _pi_get(
        f"{_base_url()}/points",
        params={
            "path": _pi_path(tag),
            "selectedFields": POINT_SELECTED_FIELDS,
        },
    )


async def get_recorded_values_by_tag(
    tag: str,
    start_time: str,
    end_time: str,
    max_count: int = 200000,
) -> dict[str, Any]:
    _point, web_id = await _get_point_and_web_id(tag)

    return await _get_stream_by_web_id(
        web_id=web_id,
        endpoint="recorded",
        params={
            "startTime": start_time,
            "endTime": end_time,
            "maxCount": max_count,
        },
    )


async def get_interpolated_values_by_tag(
    tag: str,
    start_time: str,
    end_time: str,
    interval: str,
) -> dict[str, Any]:
    if not interval:
        raise ValueError("O método interpolated exige o parâmetro interval.")

    _point, web_id = await _get_point_and_web_id(tag)

    return await _get_stream_by_web_id(
        web_id=web_id,
        endpoint="interpolated",
        params={
            "startTime": start_time,
            "endTime": end_time,
            "interval": interval,
        },
    )


async def get_summary_values_by_tag(
    tag: str,
    start_time: str,
    end_time: str,
    summary_type: str = "Average",
    summary_duration: str = "1h",
    calculation_basis: str = "TimeWeighted",
) -> dict[str, Any]:
    _point, web_id = await _get_point_and_web_id(tag)

    return await _get_stream_by_web_id(
        web_id=web_id,
        endpoint="summary",
        params={
            "startTime": start_time,
            "endTime": end_time,
            "summaryType": summary_type,
            "summaryDuration": summary_duration,
            "calculationBasis": calculation_basis,
        },
    )


async def buscar_dados_temporais_tag(
    tag: str,
    start_time: str,
    end_time: str,
    method: TemporalDataMethod | str,
    interval: str | None = None,
    summary_type: str = "Average",
    summary_duration: str = "1h",
    calculation_basis: str = "TimeWeighted",
    max_count: int = 200000,
) -> dict[str, Any]:
    method = _normalizar_metodo_temporal(method)
    point_metadata, web_id = await _get_point_and_web_id(tag)

    params: dict[str, Any] = {
        "startTime": start_time,
        "endTime": end_time,
    }

    if method == "recorded":
        endpoint = "recorded"
        params["maxCount"] = max_count

    elif method == "interpolated":
        if not interval:
            raise ValueError("O método interpolated exige o parâmetro interval.")

        endpoint = "interpolated"
        params["interval"] = interval

    else:
        endpoint = "summary"
        params.update(
            {
                "summaryType": summary_type,
                "summaryDuration": summary_duration,
                "calculationBasis": calculation_basis,
            }
        )

    raw_data = await _get_stream_by_web_id(
        web_id=web_id,
        endpoint=endpoint,
        params=params,
    )

    return {
        "tag": tag,
        "method": method,
        "point_metadata": point_metadata,
        "raw_data": raw_data,
        "params": {
            "start_time": start_time,
            "end_time": end_time,
            "interval": interval,
            "summary_type": summary_type if method == "summary" else None,
            "summary_duration": summary_duration if method == "summary" else None,
            "calculation_basis": calculation_basis if method == "summary" else None,
            "max_count": max_count if method == "recorded" else None,
        },
    }