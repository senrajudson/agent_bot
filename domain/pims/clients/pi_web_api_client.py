import json
import logging
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

import httpx

from domain.core.config import get_domain_settings

logger = logging.getLogger(__name__)

_MAX_UPSTREAM_ERROR_CHARS = 512


_DATASERVER_CACHE: dict[str, Any] = {}
_ENUM_SET_CACHE: dict[str, dict[str, Any]] = {}

TemporalDataMethod = Literal["recorded", "interpolated", "summary"]

POINT_SELECTED_FIELDS = (
    "WebId;Name;Descriptor;EngineeringUnits;PointType;DigitalSet;DigitalSetName"
)

SEARCH_SELECTED_FIELDS = (
    "Items.WebId;Items.Name;Items.Descriptor;Items.EngineeringUnits;Items.PointType;Items.DigitalSet;Items.DigitalSetName"
)


def _get_auth() -> tuple[str, str] | None:
    if get_domain_settings().PI_WEB_API_USERNAME and get_domain_settings().PI_WEB_API_PASSWORD:
        return get_domain_settings().PI_WEB_API_USERNAME, get_domain_settings().PI_WEB_API_PASSWORD

    return None


def _base_url() -> str:
    return get_domain_settings().PI_WEB_API_BASE_URL.rstrip("/")


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


def _extract_upstream_error_body(response: httpx.Response) -> str:
    """Extract a safe, truncated error message from an upstream HTTP error response.

    Attempts JSON parsing first (Errors, Error, message, detail),
    falls back to text, then to a generic HTTP status message.
    """
    status = response.status_code
    try:
        text = response.text
    except Exception:
        return f"PI Web API returned HTTP {status}"

    if not text or not text.strip():
        return f"PI Web API returned HTTP {status} without body"

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("Errors", "Error", "message", "detail"):
                val = data.get(key)
                if val is None:
                    continue
                if isinstance(val, list):
                    msg = "; ".join(str(v) for v in val[:3])
                else:
                    msg = str(val)
                if msg:
                    return msg[:_MAX_UPSTREAM_ERROR_CHARS]
        return f"PI Web API returned HTTP {status}: {text[:_MAX_UPSTREAM_ERROR_CHARS]}"
    except (json.JSONDecodeError, ValueError):
        pass

    return text[:_MAX_UPSTREAM_ERROR_CHARS]


async def _pi_get(
    url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=60,
        verify=get_domain_settings().PI_WEB_API_VERIFY_SSL,
        auth=_get_auth(),
    ) as client:
        response = await client.get(
            _normalize_pi_link(url),
            params=params,
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        safe_body = _extract_upstream_error_body(exc.response)
        raise httpx.HTTPStatusError(
            f"PI Web API error: {safe_body}",
            request=exc.request,
            response=exc.response,
        ) from exc
    return response.json()


async def _pi_post(
    url: str,
    json_body: dict[str, Any],
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=60,
        verify=get_domain_settings().PI_WEB_API_VERIFY_SSL,
        auth=_get_auth(),
    ) as client:
        response = await client.post(
            _normalize_pi_link(url),
            json=json_body,
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        safe_body = _extract_upstream_error_body(exc.response)
        raise httpx.HTTPStatusError(
            f"PI Web API error: {safe_body}",
            request=exc.request,
            response=exc.response,
        ) from exc
    return response.json()


def _pi_path(tag: str) -> str:
    tag_limpa = str(tag or "").strip()

    if not tag_limpa:
        raise ValueError("Tag vazia ou inválida.")

    return f"\\\\{get_domain_settings().PI_SERVER_NAME}\\{tag_limpa}"


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


async def _get_point_and_web_id(
    tag: str, *, resolver=None
) -> tuple[dict[str, Any], str]:
    if resolver is not None:
        resolution = await resolver(tag)
        if resolution.is_resolved and resolution.items:
            point = resolution.items[0]
            return point, _get_web_id(point)
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


async def get_value_at_or_before_by_web_id(
    web_id: str,
    time: str,
) -> dict[str, Any]:
    """GET /streams/{webId}/recorded — último valor em ou antes de `time`.

    Retorna o último ponto registrado com timestamp ≤ `time`.
    Reutiliza WebId já resolvido, sem nova resolução de PI Point.
    """
    return await _get_stream_by_web_id(
        web_id=web_id,
        endpoint="recorded",
        params={
            "endTime": time,
            "maxCount": 1,
            "sortOrder": "desc",
        },
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


def build_resolution_only_batch_request(tag: str) -> dict[str, Any]:
    """Sub-batch minimal: 1 sub-request GET /points?path=... com selectedFields.

    Diferente de build_tags_batch_request (que faz point + value + 9 attributes),
    este carrega apenas point_0, suficiente para validar existência.
    """
    batch_request: dict[str, Any] = {}
    base_url = _base_url()
    pi_path = _pi_path(tag)

    batch_request["point_0"] = {
        "Method": "GET",
        "Resource": (
            f"{base_url}/points"
            f"?path={pi_path}"
            f"&selectedFields={POINT_SELECTED_FIELDS}"
        ),
    }
    return batch_request


async def get_data_server() -> dict[str, Any]:
    cache_key = get_domain_settings().PI_SERVER_NAME.upper()

    if cache_key in _DATASERVER_CACHE:
        return _DATASERVER_CACHE[cache_key]

    data = await _pi_get(f"{_base_url()}/dataservers")
    items = data.get("Items") or []

    if not items:
        raise RuntimeError("Nenhum Data Server foi retornado pela PI Web API.")

    server_name = get_domain_settings().PI_SERVER_NAME.lower()

    for item in items:
        name = str(item.get("Name") or "").lower()

        if name == server_name:
            _DATASERVER_CACHE[cache_key] = item
            return item

    raise RuntimeError(f"Data Server {get_domain_settings().PI_SERVER_NAME} não encontrado.")


async def get_dataservers() -> dict[str, Any]:
    """GET /dataservers — checagem pontual de conectividade.

    Diferente de get_data_server(), esta função:
    - Não usa cache.
    - Retorna a lista completa de Items.
    - Captura erros de rede/HTTP em vez de lançar exceção.

    Retorna dict com endpoint, status_code, items, error.
    """
    endpoint = f"{_base_url()}/dataservers"

    try:
        data = await _pi_get(endpoint)
        items = data.get("Items") or []
        return {
            "endpoint": endpoint,
            "status_code": 200,
            "items": items,
            "error": None,
        }
    except httpx.HTTPStatusError as e:
        return {
            "endpoint": endpoint,
            "status_code": e.response.status_code,
            "items": [],
            "error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
        }
    except httpx.RequestError as e:
        return {
            "endpoint": endpoint,
            "status_code": None,
            "items": [],
            "error": f"Request failed: {e}",
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "status_code": None,
            "items": [],
            "error": f"Unexpected error: {e}",
        }


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


async def get_point_attributes(tag: str) -> dict[str, Any]:
    """GET /points/{webId}/attributes — payload completo, sem filtro."""
    _point, web_id = await _get_point_and_web_id(tag)
    return await _pi_get(f"{_base_url()}/points/{web_id}/attributes")


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
    *,
    resolver=None,
) -> dict[str, Any]:
    method = _normalizar_metodo_temporal(method)
    point_metadata, web_id = await _get_point_and_web_id(tag, resolver=resolver)

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


async def search_pi_points(
    query: str,
    max_count: int = 20,
    selected_fields: str | None = None,
) -> dict[str, Any]:
    """Busca PI Points via /points/search (PI Point Search Syntax)."""
    data_server = await get_data_server()
    web_id = data_server["WebId"]
    params: dict[str, Any] = {
        "dataServerWebId": web_id,
        "query": query,
        "maxCount": max_count,
    }
    if selected_fields:
        params["selectedFields"] = selected_fields
    else:
        params["selectedFields"] = POINT_SELECTED_FIELDS

    return await _pi_get(
        f"{_base_url()}/points/search",
        params=params,
    )


async def get_points_by_name_filter(
    name_filter: str,
    max_count: int = 20,
    selected_fields: str | None = None,
) -> dict[str, Any]:
    """Busca PI Points por nome via /dataservers/{webId}/points?nameFilter=."""
    data_server = await get_data_server()
    web_id = data_server["WebId"]

    params: dict[str, Any] = {
        "nameFilter": name_filter,
    }
    if selected_fields:
        params["selectedFields"] = selected_fields
    else:
        params["selectedFields"] = POINT_SELECTED_FIELDS

    return await _pi_get(
        f"{_base_url()}/dataservers/{web_id}/points",
        params=params,
    )


async def search_points_by_digital_set(
    digital_set_name: str,
    max_count: int = 100,
    start_index: int = 0,
    selected_fields: str | None = None,
) -> dict[str, Any]:
    """Busca PI Points digitais por DigitalSet via /points/search com filtro nativo."""
    data_server = await get_data_server()
    web_id = data_server["WebId"]

    params: dict[str, Any] = {
        "dataServerWebId": web_id,
        "query": f'PointType:=Digital AND DigitalSet:="{digital_set_name}"',
        "startIndex": start_index,
        "maxCount": max_count,
        "selectedFields": selected_fields or SEARCH_SELECTED_FIELDS,
    }

    return await _pi_get(
        f"{_base_url()}/points/search",
        params=params,
    )