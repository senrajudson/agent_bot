import re
from typing import Any

from domain.core.config import settings

_LIMIT_ALERTA_ABSOLUTO = 50
_LIMIT_ALERTA_PERCENTUAL = 0.01

_CRITICAL_KEYWORDS = (
    "error", "erro", "failed", "failure", "exception", "traceback",
    "fatal", "unavailable", "down", "offline", "refused",
    "connection refused", "broken pipe", "panic",
)

_ALERT_KEYWORDS = (
    "warning", "warn", "retry", "slow", "timeout", "backoff",
    "bad request", "unauthorized", "forbidden",
)

_INFO_PATTERNS = (
    "healthy", "ok", "started", "ready", "listening",
)

_HTTP_CODE_REGEX = re.compile(r"(?<![\d.:])(\d{3})(?![\d.])")

_LIMIT_CLIENT_ABORTED_ABSOLUTO_OPERACIONAL = 1000
_LIMIT_CLIENT_ABORTED_PERCENTUAL_OPERACIONAL = 0.20

_CLIENT_ABORTED_KEYWORDS = (
    "client aborted",
    "client closed request",
    "client canceled",
)

_MENSAGENS_POR_NIVEL = {
    "EXCELENTE": "O ambiente está excelente, sem sinais relevantes de falha.",
    "SAUDÁVEL": "O ambiente está saudável. Há apenas registros normais ou ruído operacional baixo.",
    "OPERACIONAL": "O ambiente está operacional. O PIMS responde normalmente, mas há ocorrências não críticas, como cancelamentos de requisições por clientes.",
    "ALERTA": "O ambiente está em alerta. Há sinais que podem afetar consultas ou consumidores.",
    "CRÍTICO": "O ambiente está crítico. Há falhas relevantes que exigem ação.",
    "OFFLINE": "O ambiente parece offline ou inacessível.",
}


def _extract_http_status(line: str) -> str | None:
    codes = _HTTP_CODE_REGEX.findall(line)
    return codes[-1] if codes else None


def _classify_line(line: str) -> str:
    code = _extract_http_status(line)
    low = line.lower()

    if code:
        if code.startswith("5"):
            return "erro_critico"
        if code == "499":
            return "client_aborted"
        if code.startswith("4") and any(kw in low for kw in _CLIENT_ABORTED_KEYWORDS):
            return "client_aborted"
        if code.startswith("4"):
            return "alerta_real"
        if code.startswith("2") or code == "304":
            if any(kw in low for kw in _ALERT_KEYWORDS):
                return "ignorado_benigno"
            return "informativo"

    if any(kw in low for kw in _CRITICAL_KEYWORDS):
        return "erro_critico"
    if any(kw in low for kw in _ALERT_KEYWORDS):
        return "alerta_real"
    if any(kw in low for kw in _INFO_PATTERNS):
        return "informativo"
    return "ignorado_benigno"


def _extract_loki_lines(loki_response: dict[str, Any]) -> list[str]:
    data = loki_response.get("data", {})
    result = data.get("result", [])

    lines: list[str] = []

    for stream in result:
        values = stream.get("values", [])

        for value in values:
            if len(value) >= 2:
                lines.append(str(value[1]))

    return lines


def _build_status_summary(lines: list[str]) -> dict[str, Any]:
    erros_criticos: list[str] = []
    alertas_reais: list[str] = []
    client_aborted_lines: list[str] = []
    informativos: list[str] = []
    ignorados_benignos: list[str] = []

    for line in lines:
        cat = _classify_line(line)
        if cat == "erro_critico":
            erros_criticos.append(line)
        elif cat == "alerta_real":
            alertas_reais.append(line)
        elif cat == "client_aborted":
            client_aborted_lines.append(line)
        elif cat == "ignorado_benigno":
            ignorados_benignos.append(line)
        else:
            informativos.append(line)

    return {
        "total_logs": len(lines),
        "erros_criticos": len(erros_criticos),
        "alertas_reais": len(alertas_reais),
        "client_aborted": len(client_aborted_lines),
        "informativos": len(informativos),
        "ignorados_benignos": len(ignorados_benignos),
        "total_errors": len(erros_criticos),
        "total_warnings": len(alertas_reais),
        "recent_critical": erros_criticos[-5:],
        "recent_real_alerts": alertas_reais[-5:],
        "recent_client_aborted": client_aborted_lines[-5:],
        "recent_info": informativos[-5:],
        "recent_benign_ignored": ignorados_benignos[-5:],
        "recent_errors": erros_criticos[-5:],
        "recent_warnings": alertas_reais[-5:],
        "recent_logs": lines[-5:],
    }


def _build_veredito(
    summary: dict[str, Any],
    dataserver_veredito: str = "CONECTADO",
) -> str:
    erros = summary.get("erros_criticos", 0)
    alertas = summary.get("alertas_reais", 0)
    aborted = summary.get("client_aborted", 0)
    total = summary.get("total_logs", 0)
    informativos = summary.get("informativos", 0)

    # 1: OFFLINE — DS indisponível e sem logs
    if dataserver_veredito == "INDISPONÍVEL" and total == 0:
        return "OFFLINE"
    # 2: CRÍTICO — erros críticos
    if erros > 0:
        return "CRÍTICO"
    # 3: CRÍTICO — DS desconectado com alertas
    if dataserver_veredito == "DESCONECTADO" and alertas > 0:
        return "CRÍTICO"
    # 4: ALERTA — alertas acima do limite absoluto
    if alertas >= _LIMIT_ALERTA_ABSOLUTO:
        return "ALERTA"
    # 5: ALERTA — alertas acima do limite percentual
    if total > 0 and alertas / total >= _LIMIT_ALERTA_PERCENTUAL:
        return "ALERTA"
    # 6: ALERTA — client_aborted acima do limite
    if aborted >= _LIMIT_CLIENT_ABORTED_ABSOLUTO_OPERACIONAL:
        return "ALERTA"
    if total > 0 and aborted / total >= _LIMIT_CLIENT_ABORTED_PERCENTUAL_OPERACIONAL:
        return "ALERTA"
    # 7: ALERTA — DS não-conectado (inclui INDISPONÍVEL com logs — R4=B)
    if dataserver_veredito in ("DESCONECTADO", "INCONFIÁVEL", "AUSENTE", "INDISPONÍVEL"):
        return "ALERTA"
    # 8: OPERACIONAL — client_aborted presente mas abaixo do limite
    if aborted > 0 and erros == 0 and alertas < _LIMIT_ALERTA_ABSOLUTO:
        if total == 0 or alertas / total < _LIMIT_ALERTA_PERCENTUAL:
            return "OPERACIONAL"
    # 9: SAUDÁVEL — sem logs mas DS conectado
    if total == 0 and dataserver_veredito == "CONECTADO":
        return "SAUDÁVEL"
    # 10: EXCELENTE — sem falhas e com informativos
    if erros == 0 and alertas == 0 and aborted == 0 and informativos > 0:
        return "EXCELENTE"
    # 11: Fallback
    return "SAUDÁVEL"


def _build_status_output(
    summary: dict[str, Any],
    dataserver_veredito: str = "CONECTADO",
) -> str:
    total_logs = summary.get("total_logs", 0)
    erros = summary.get("erros_criticos", 0)
    alertas = summary.get("alertas_reais", 0)
    client_aborted = summary.get("client_aborted", 0)
    informativos = summary.get("informativos", 0)
    ignorados = summary.get("ignorados_benignos", 0)
    recent_critical = summary.get("recent_critical", [])
    recent_real_alerts = summary.get("recent_real_alerts", [])
    recent_client_aborted = summary.get("recent_client_aborted", [])
    veredito = _build_veredito(summary, dataserver_veredito)
    frase = _MENSAGENS_POR_NIVEL.get(veredito, "")

    lines = [
        f"Status do PIMS: {veredito}",
        frase,
        "Resumo determinístico dos logs do PIMS:",
        f"Total de logs consultados: {total_logs}",
        f"Erros críticos encontrados: {erros}",
        f"Alertas reais encontrados: {alertas}",
    ]

    if client_aborted > 0:
        lines.append(
            f"Cancelamentos de requisições "
            f"(HTTP 499 / client aborted): {client_aborted}"
        )

    if informativos > 0:
        lines.append(f"Registros informativos encontrados: {informativos}")

    if ignorados > 0:
        lines.append(
            f"Registros benignos ignorados "
            f"(HTTP 2xx/304 com palavra de alerta): {ignorados}"
        )

    if recent_critical:
        lines.append("\nErros críticos recentes:")
        lines.extend(f"- {line}" for line in recent_critical[:5])

    if recent_real_alerts:
        lines.append("\nAlertas reais recentes:")
        lines.extend(f"- {line}" for line in recent_real_alerts[:5])

    if recent_client_aborted:
        lines.append("\nCancelamentos recentes (HTTP 499 / client aborted):")
        lines.extend(f"- {line}" for line in recent_client_aborted[:5])

    if total_logs == 0:
        lines.append(
            "\nNão há logs suficientes no período consultado. "
            "Status baseado apenas no check de conectividade do DataServer."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — PI Web API / DataServer check
# ---------------------------------------------------------------------------


def _normalize_dataserver_response(raw: dict[str, Any]) -> dict[str, Any]:
    endpoint = raw.get("endpoint", "")
    items = raw.get("items") or []
    error = raw.get("error")
    return {
        "endpoint": endpoint,
        "items": items,
        "items_count": len(items),
        "error": error,
    }


def _select_expected_dataserver(
    items: list[dict[str, Any]],
    expected_name: str,
) -> tuple[bool, dict[str, Any] | None, list[str]]:
    available_names: list[str] = []

    for item in items:
        name = str(item.get("Name") or "").strip()

        if name:
            available_names.append(name)

            if name.lower() == expected_name.lower():
                return True, item, available_names

    if len(items) == 1:
        return True, items[0], available_names

    return False, None, available_names


def _build_dataserver_veredito(
    matched: bool,
    is_connected: bool | None,
    has_required_fields: bool,
    error: str | None,
) -> str:
    if error:
        return "INDISPONÍVEL"
    if not matched:
        return "AUSENTE"
    if is_connected is None or not has_required_fields:
        return "INCONFIÁVEL"
    if is_connected is True:
        return "CONECTADO"
    return "DESCONECTADO"


def _build_dataserver_output(
    endpoint: str,
    veredito: str,
    dataserver_info: dict[str, Any],
    error: str | None,
) -> str:
    lines = [
        "",
        "PI Web API / DataServer",
        f"Endpoint consultado: {endpoint}",
        f"Veredito: {veredito}",
    ]

    if not error and dataserver_info.get("matched"):
        ds = dataserver_info
        lines.append(f"Name: {ds.get('name', 'N/A')}")

        if ds.get("web_id"):
            lines.append(f"WebId: {ds['web_id']}")

        lines.append(f"IsConnected: {ds.get('is_connected', 'N/A')}")

        if ds.get("server_version"):
            lines.append(f"ServerVersion: {ds['server_version']}")

        if ds.get("server_time"):
            lines.append(f"ServerTime: {ds['server_time']}")

        if ds.get("path"):
            lines.append(f"Path: {ds['path']}")

    if error:
        lines.append(f"Erro: {error}")

    return "\n".join(lines)


_OVERALL_STATUS_MAP = {
    "EXCELENTE":   ("excellent",  "warning"),
    "SAUDÁVEL":    ("healthy",    "warning"),
    "OPERACIONAL": ("operational", "warning"),
    "ALERTA":      ("warning",    "warning"),
    "CRÍTICO":     ("critical",   "critical"),
    "OFFLINE":     ("offline",    "offline"),
}


def _build_overall_status(veredito_logs: str, veredito_ds: str) -> str:
    if veredito_logs in _OVERALL_STATUS_MAP:
        conectado, outro = _OVERALL_STATUS_MAP[veredito_logs]
        return conectado if veredito_ds == "CONECTADO" else outro
    # Defensive fallbacks para rótulos legados (não-produzidos, aceitos sem quebrar)
    if veredito_logs in ("NORMAL",):
        return "healthy" if veredito_ds == "CONECTADO" else "warning"
    if veredito_logs == "OK":
        return "healthy" if veredito_ds == "CONECTADO" else "warning"
    if veredito_logs == "INDETERMINADO":
        return "indeterminate"
    return "indeterminate"


async def _fetch_dataserver_info() -> dict[str, Any]:
    from domain.pims.clients.pi_web_api_client import get_dataservers

    try:
        raw = await get_dataservers()
        normalized = _normalize_dataserver_response(raw)
        expected_name = settings.PI_SERVER_NAME
        matched, item, available = _select_expected_dataserver(
            normalized["items"], expected_name
        )

        is_connected = None
        web_id = None
        name = None
        server_version = None
        server_time = None
        path_val = None
        has_required_fields = False

        if item:
            is_connected = item.get("IsConnected")
            web_id = item.get("WebId")
            name = item.get("Name")
            server_version = item.get("ServerVersion")
            server_time = item.get("ServerTime")
            path_val = item.get("Path")
            has_required_fields = bool(web_id and server_version)

        veredito = _build_dataserver_veredito(
            matched, is_connected, has_required_fields, raw.get("error")
        )

        dataserver_info = {
            "endpoint": normalized["endpoint"],
            "ok": veredito in ("CONECTADO", "DESCONECTADO"),
            "veredito": veredito,
            "items_count": normalized["items_count"],
            "expected_name": expected_name,
            "matched": matched,
            "web_id": web_id,
            "name": name,
            "is_connected": is_connected,
            "server_version": server_version,
            "server_time": server_time,
            "path": path_val,
            "error": raw.get("error"),
            "available_names": available,
        }

        output_text = _build_dataserver_output(
            normalized["endpoint"],
            veredito,
            dataserver_info,
            raw.get("error"),
        )
        dataserver_info["output_text"] = output_text
        return dataserver_info

    except Exception as e:
        base_url = settings.PI_WEB_API_BASE_URL.rstrip("/")
        endpoint = f"{base_url}/dataservers"
        output_text = (
            f"\n\nPI Web API / DataServer\n"
            f"Endpoint consultado: {endpoint}\n"
            f"Veredito: INDISPONÍVEL\n"
            f"Erro: {e}"
        )
        return {
            "endpoint": endpoint,
            "ok": False,
            "veredito": "INDISPONÍVEL",
            "items_count": 0,
            "expected_name": settings.PI_SERVER_NAME,
            "matched": False,
            "web_id": None,
            "name": None,
            "is_connected": None,
            "server_version": None,
            "server_time": None,
            "path": None,
            "error": str(e),
            "available_names": [],
            "output_text": output_text,
        }


async def consultar_status_pims_service(
    user_message: str = "",
    query: str | None = None,
    lookback_minutes: int | None = None,
    limit: int | None = None,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    from domain.pims_ops.clients.grafana_loki_client import query_loki_range

    query_final = query or settings.PIMS_STATUS_LOKI_QUERY
    lookback_final = lookback_minutes or settings.PIMS_STATUS_LOOKBACK_MINUTES
    limit_final = limit or settings.PIMS_STATUS_LIMIT

    try:
        loki_response = await query_loki_range(
            query=query_final,
            lookback_minutes=lookback_final,
            limit=limit_final,
        )

        lines = _extract_loki_lines(loki_response)
        summary = _build_status_summary(lines)
        output = _build_status_output(summary, "CONECTADO")

    except Exception as error:
        return {
            "ok": False,
            "tool_name": "status_pims_tool",
            "tool_result": {
                "query": query_final,
                "lookback_minutes": lookback_final,
                "limit": limit_final,
                "error": str(error),
            },
            "output": (
                "Não consegui consultar os logs do PIMS no Grafana/Loki. "
                f"Erro: {error}"
            ),
            "answer_generation_error": None,
        }

    tool_result = {
        "query": query_final,
        "lookback_minutes": lookback_final,
        "limit": limit_final,
        "summary": summary,
    }

    if include_raw_response:
        tool_result["raw_loki_response"] = loki_response

    dataserver_info = await _fetch_dataserver_info()
    output_combined = f"{output}\n{dataserver_info['output_text']}"
    tool_result["dataserver_check"] = {
        k: v for k, v in dataserver_info.items() if k != "output_text"
    }

    veredito_logs = _build_veredito(summary, dataserver_info["veredito"])
    tool_result["status"] = veredito_logs
    tool_result["overall_status"] = _build_overall_status(
        veredito_logs, dataserver_info["veredito"]
    )

    return {
        "ok": True,
        "tool_name": "status_pims_tool",
        "tool_result": tool_result,
        "output": output_combined,
        "answer_generation_error": None,
    }