from typing import Any

from clients.grafana_loki_client import query_loki_range
from core.config import settings


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
    error_keywords = [
        "error",
        "erro",
        "failed",
        "failure",
        "timeout",
        "unavailable",
        "down",
        "exception",
        "refused",
        "offline",
    ]

    warning_keywords = [
        "warn",
        "warning",
        "lento",
        "slow",
        "retry",
    ]

    error_lines = [
        line for line in lines
        if any(keyword in line.lower() for keyword in error_keywords)
    ]

    warning_lines = [
        line for line in lines
        if any(keyword in line.lower() for keyword in warning_keywords)
    ]

    return {
        "total_logs": len(lines),
        "total_errors": len(error_lines),
        "total_warnings": len(warning_lines),
        "recent_errors": error_lines[-10:],
        "recent_warnings": warning_lines[-10:],
        "recent_logs": lines[-10:],
    }


def _build_status_output(summary: dict[str, Any]) -> str:
    total_logs = summary.get("total_logs", 0)
    total_errors = summary.get("total_errors", 0)
    total_warnings = summary.get("total_warnings", 0)
    recent_errors = summary.get("recent_errors", [])
    recent_warnings = summary.get("recent_warnings", [])

    lines = [
        "Resumo determinístico dos logs do PIMS:",
        f"Total de logs consultados: {total_logs}",
        f"Total de erros encontrados: {total_errors}",
        f"Total de alertas encontrados: {total_warnings}",
    ]

    if recent_errors:
        lines.append("\nErros recentes:")
        lines.extend(f"- {line}" for line in recent_errors[:5])

    if recent_warnings:
        lines.append("\nAlertas recentes:")
        lines.extend(f"- {line}" for line in recent_warnings[:5])

    if total_logs == 0:
        lines.append("\nNão há logs suficientes no período consultado.")

    return "\n".join(lines)


async def consultar_status_pims_service(
    user_message: str = "",
    query: str | None = None,
    lookback_minutes: int | None = None,
    limit: int | None = None,
    include_raw_response: bool = False,
) -> dict[str, Any]:
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
        output = _build_status_output(summary)

    except Exception as error:
        return {
            "ok": False,
            "tool_name": "status_pims",
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

    return {
        "ok": True,
        "tool_name": "status_pims",
        "tool_result": tool_result,
        "output": output,
        "answer_generation_error": None,
    }