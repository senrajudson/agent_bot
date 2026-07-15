from __future__ import annotations

import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from domain.analytics.clients.math_tool_client import (
    call_calculate,
    call_calculus,
    call_stats,
)
from domain.analytics.utils.math_expression import limpar_expressao_basica
from domain.analytics.utils.math_pi_series import (
    buscar_serie_pi,
    extrair_point_metadata,
    extrair_points,
    extrair_values,
)
from domain.analytics.utils.math_time_unit import detectar_time_unit
from domain.analytics.utils.math_units import inferir_time_unit_por_unidade

logger = logging.getLogger(__name__)

_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
    socket.gaierror,
    ConnectionError,
    OSError,
)


DATA_METHODS_VALIDOS = {"recorded", "interpolated", "summary"}


def _extrair_eng_unit(point_metadata: dict[str, Any]) -> str:
    return (
        point_metadata.get("EngineeringUnits")
        or point_metadata.get("EngUnits")
        or point_metadata.get("engunits")
        or point_metadata.get("EngUnitsAbbreviation")
        or ""
    )


def _normalizar_data_method(data_method: str | None) -> str:
    method = str(data_method or "interpolated").strip().lower()

    if method not in DATA_METHODS_VALIDOS:
        raise ValueError("data_method inválido. Use recorded, interpolated ou summary.")

    return method


def _build_glosa(operation: str, data_method: str) -> str:
    if data_method == "summary":
        return f"agregação por resumo ({operation})"
    if data_method == "recorded":
        return f"dados brutos registrados ({operation})"
    if data_method == "interpolated":
        return f"valores interpolados ({operation})"
    return f"estatística ({operation})"


def _parametros_temporais(
    data_method: str,
    interval: str | None,
    summary_type: str,
    summary_duration: str,
    calculation_basis: str,
    max_count: int,
) -> dict[str, Any]:
    return {
        "data_method": data_method,
        "interval": interval if data_method == "interpolated" else None,
        "max_count": max_count if data_method == "recorded" else None,
        "summary_type": summary_type if data_method == "summary" else None,
        "summary_duration": summary_duration if data_method == "summary" else None,
        "calculation_basis": calculation_basis if data_method == "summary" else None,
    }


GROUP_BY_VALIDOS = {"1h", "1d", "1w", "1mo"}


def _normalizar_group_by(value: str | None) -> str | None:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    v = str(value).strip().lower()

    mapping: dict[str, str] = {
        "1h": "1h", "1 hora": "1h", "hora": "1h", "hour": "1h",
        "hourly": "1h", "por hora": "1h",
        "1d": "1d", "1 dia": "1d", "dia": "1d", "day": "1d",
        "daily": "1d", "diário": "1d", "diario": "1d",
        "1mo": "1mo", "1 mês": "1mo", "1 mes": "1mo",
        "mês": "1mo", "mes": "1mo", "month": "1mo", "monthly": "1mo", "mensal": "1mo",
        "1w": "1w", "1 semana": "1w", "semana": "1w", "week": "1w",
        "weekly": "1w", "semanal": "1w",
    }

    if v in mapping:
        return mapping[v]

    raise ValueError(
        f"group_by inválido: '{value}'. Valores aceitos: 1h, 1d, 1w, 1mo."
    )


def _unit_to_seconds_factor(eng_unit: str | None) -> int | None:
    if not eng_unit:
        return None
    u = str(eng_unit).lower()
    if "/h" in u or "/hr" in u or "por hora" in u:
        return 3600
    if "/min" in u or "por minuto" in u:
        return 60
    if "/s" in u or "por segundo" in u:
        return 1
    return None


def _inferir_unidade_volume(eng_unit: str | None) -> str:
    if not eng_unit:
        return "unidade arbitrária"
    u = str(eng_unit).strip()
    for suffix in ["/h", "/H", "/hr", "/HR", "/min", "/MIN", "/s", "/S"]:
        if u.endswith(suffix):
            return u[: -len(suffix)]
    return u


def _build_glosa_serie(operation: str, eng_unit: str | None) -> str:
    if eng_unit and _unit_to_seconds_factor(eng_unit) is not None:
        return f"consumo calculado como média do bloco × duração do bloco ({operation})"
    return f"{operation} por período"


async def executar_calculo_simples_service(
    expression: str,
) -> dict[str, Any]:
    expression_limpa = limpar_expressao_basica(expression)
    payload = {"expression": expression_limpa}

    try:
        result = await call_calculate(payload)

        return {
            "ok": True,
            "tool_name": "calculator_tool",
            "tool_result": {
                "endpoint": "/calculate",
                "payload": payload,
                "result": result,
            },
            "output": json.dumps(result, ensure_ascii=False),
            "answer_generation_error": None,
        }

    except _NETWORK_ERRORS as error:
        logger.warning("Math Tool /calculate unreachable: %s", error)
        return {
            "ok": False,
            "tool_name": "calculator_tool",
            "tool_result": {
                "endpoint": "/calculate",
                "payload": payload,
                "error": str(error),
            },
            "output": (
                "Serviço de cálculo matemático temporariamente indisponível "
                "(erro de rede). Tente novamente em instantes."
            ),
            "answer_generation_error": str(error),
        }

    except Exception as error:
        return {
            "ok": False,
            "tool_name": "calculator_tool",
            "tool_result": {
                "endpoint": "/calculate",
                "payload": payload,
                "error": str(error),
            },
            "output": f"Não consegui executar o cálculo simples. Erro: {error}",
            "answer_generation_error": str(error),
        }


def _arredondar_resultado_stats(result: dict[str, Any], operation: str, casas: int = 2) -> dict[str, Any]:
    result_output = json.loads(json.dumps(result, ensure_ascii=False))

    valor = (
        result_output
        .get("result", {})
        .get(operation)
    )

    if isinstance(valor, (int, float)):
        result_output["result"][operation] = round(valor, casas)

    return result_output


def _group_by_nominal_seconds(group_by: str) -> float:
    nom = {"1h": 3600.0, "1d": 86400.0, "1w": 604800.0, "1mo": 2592000.0}
    return nom.get(group_by, 3600.0)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _format_bucket_label(dt: datetime) -> str:
    return dt.strftime("%d/%m")


def _duracao_bloco_segundos(points: list[dict], group_by: str) -> float:
    if len(points) >= 2:
        t0 = _parse_ts(points[0]["timestamp"])
        t1 = _parse_ts(points[-1]["timestamp"])
        delta = (t1 - t0).total_seconds()
        if delta > 0:
            return delta
    return _group_by_nominal_seconds(group_by)


def _group_points_by_period(
    points: list[dict], group_by: str, start_time: str, end_time: str
) -> list[dict]:
    t_start = _parse_ts(start_time)
    t_end = _parse_ts(end_time) if end_time != "*" else datetime.now(timezone.utc)

    step_map = {"1h": timedelta(hours=1), "1d": timedelta(days=1),
                "1w": timedelta(weeks=1), "1mo": timedelta(days=30)}
    step = step_map.get(group_by, timedelta(hours=1))

    tz = t_start.tzinfo

    buckets = []
    current = t_start
    while current < t_end:
        next_bound = current + step
        if next_bound > t_end:
            next_bound = t_end
        bucket_points = []
        for p in points:
            pt = _parse_ts(p["timestamp"])
            if pt.tzinfo is None and tz is not None:
                pt = pt.replace(tzinfo=tz)
            if pt.tzinfo is not None and tz is None:
                pt = pt.replace(tzinfo=None)
            if current <= pt < next_bound:
                bucket_points.append(p)

        buckets.append({
            "period_start": current.isoformat(),
            "period_end": next_bound.isoformat(),
            "points": bucket_points,
            "label": _format_bucket_label(current),
            "duration_seconds": (next_bound - current).total_seconds(),
        })
        current = next_bound

    return buckets


def _calcular_consumo_por_periodo(
    buckets: list[dict], eng_unit: str, operation: str
) -> tuple[list[dict], float | None]:
    series_items = []
    total_valido = 0.0
    tem_valido = False

    seconds_factor = _unit_to_seconds_factor(eng_unit)
    unidade_final = _inferir_unidade_volume(eng_unit)

    for bucket in buckets:
        bp = bucket["points"]
        dur = bucket["duration_seconds"]
        if dur <= 0:
            dur = _group_by_nominal_seconds("1d")

        if not bp:
            series_items.append({
                "label": bucket["label"],
                "period_start": bucket["period_start"],
                "period_end": bucket["period_end"],
                "value": None,
                "unit": unidade_final,
                "quality": "sem dados",
            })
            continue

        values_bucket = [p["value"] for p in bp if p.get("value") is not None]
        if not values_bucket:
            series_items.append({
                "label": bucket["label"],
                "period_start": bucket["period_start"],
                "period_end": bucket["period_end"],
                "value": None,
                "unit": unidade_final,
                "quality": "bad",
            })
            continue

        if seconds_factor is not None and operation == "sum":
            media = sum(values_bucket) / len(values_bucket)
            valor = round(media * (dur / seconds_factor), 2)
            unit_out = unidade_final
        elif operation == "sum":
            valor = round(sum(values_bucket), 2)
            unit_out = unidade_final
        elif operation == "mean":
            valor = round(sum(values_bucket) / len(values_bucket), 2)
            unit_out = eng_unit or unidade_final
        elif operation == "max":
            valor = round(max(values_bucket), 2)
            unit_out = eng_unit or unidade_final
        elif operation == "min":
            valor = round(min(values_bucket), 2)
            unit_out = eng_unit or unidade_final
        elif operation == "count":
            valor = len(values_bucket)
            unit_out = ""
        elif operation == "median":
            sorted_vals = sorted(values_bucket)
            n = len(sorted_vals)
            if n % 2 == 1:
                valor = round(sorted_vals[n // 2], 2)
            else:
                valor = round((sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2, 2)
            unit_out = eng_unit or unidade_final
        elif operation == "range":
            valor = round(max(values_bucket) - min(values_bucket), 2)
            unit_out = eng_unit or unidade_final
        elif operation == "stddev_population":
            m = sum(values_bucket) / len(values_bucket)
            var = sum((x - m) ** 2 for x in values_bucket) / len(values_bucket)
            valor = round(var ** 0.5, 2)
            unit_out = eng_unit or unidade_final
        else:
            valor = round(sum(values_bucket), 2)
            unit_out = unidade_final

        series_items.append({
            "label": bucket["label"],
            "period_start": bucket["period_start"],
            "period_end": bucket["period_end"],
            "value": valor,
            "unit": unit_out,
            "quality": "good",
        })
        total_valido += (valor if isinstance(valor, (int, float)) else 0)
        tem_valido = True

    total_geral = round(total_valido, 2) if tem_valido else None
    return series_items, total_geral


async def executar_estatistica_tags_service(
    tags: list[str],
    operation: str,
    start_time: str,
    end_time: str = "*",
    interval: str | None = None,
    max_count: int = 200000,
    data_method: str | None = "interpolated",
    summary_type: str = "Average",
    summary_duration: str = "1h",
    calculation_basis: str = "TimeWeighted",
    group_by: str | None = None,
    return_series: bool = False,
) -> dict[str, Any]:
    outputs = []
    results = []

    try:
        method = _normalizar_data_method(data_method)

        group_by_normalizado = _normalizar_group_by(group_by)
        output_mode = "series" if (group_by_normalizado is not None or return_series) else "scalar"
        if output_mode == "series" and method != "summary":
            method = "summary"
            summary_type = summary_type or "Average"
            summary_duration = summary_duration or "1h"
            calculation_basis = calculation_basis or "TimeWeighted"

        for tag in tags:
            pi_response = await buscar_serie_pi(
                tag=tag,
                start_time=start_time,
                end_time=end_time,
                interval=interval,
                max_count=max_count,
                data_method=method,
                summary_type=summary_type,
                summary_duration=summary_duration,
                calculation_basis=calculation_basis,
            )

            if output_mode == "series":
                points = extrair_points(pi_response)
                point_metadata = extrair_point_metadata(pi_response)
                unidade_da_tag = _extrair_eng_unit(point_metadata) or "sem unidade cadastrada"

                gb = group_by_normalizado or summary_duration or "1d"
                buckets = _group_points_by_period(
                    points=points, group_by=gb,
                    start_time=start_time, end_time=end_time,
                )

                series_items, total_geral = _calcular_consumo_por_periodo(
                    buckets=buckets, eng_unit=unidade_da_tag, operation=operation,
                )

                unidade_final = _inferir_unidade_volume(unidade_da_tag)
                glosa = _build_glosa_serie(operation, unidade_da_tag)
                periodo_efetivo = f"{start_time} a {end_time}"

                params_temporais = _parametros_temporais(
                    data_method=method, interval=interval,
                    summary_type=summary_type, summary_duration=summary_duration,
                    calculation_basis=calculation_basis, max_count=max_count,
                )

                result_item = {
                    "tag": tag, "endpoint": "/stats",
                    "operation": operation,
                    "series": series_items, "total": total_geral,
                    "unidade_da_tag": unidade_da_tag,
                    "unidade_final_inferida": unidade_final,
                    "quantidade_amostras": len(points),
                    "group_by": gb,
                    **params_temporais,
                }

                output_item = {
                    "tag": tag, "operation": operation,
                    "group_by": gb,
                    "unidade_da_tag": unidade_da_tag,
                    "unidade_final_inferida": unidade_final,
                    "periodo_efetivo": periodo_efetivo,
                    "glosa_interpretativa": glosa,
                    "quantidade_amostras": len(points),
                    "total": total_geral,
                    "series": series_items,
                    **params_temporais,
                }

                results.append(result_item)
                outputs.append(output_item)
                continue

            values = extrair_values(pi_response)

            if not values:
                raise ValueError(
                    f"A tag {tag} não possui valores numéricos válidos no período."
                )

            point_metadata = extrair_point_metadata(pi_response)
            unidade_da_tag = _extrair_eng_unit(point_metadata) or "sem unidade cadastrada"

            payload = {
                "values": values,
                "operations": [operation],
            }

            result = await call_stats(payload)
            result = _arredondar_resultado_stats(result, operation, casas=2)

            params_temporais = _parametros_temporais(
                data_method=method,
                interval=interval,
                summary_type=summary_type,
                summary_duration=summary_duration,
                calculation_basis=calculation_basis,
                max_count=max_count,
            )

            result_item = {
                "tag": tag,
                "endpoint": "/stats",
                "payload": payload,
                "result": result,
                "unidade_da_tag": unidade_da_tag,
                "quantidade_amostras": len(values),
                **params_temporais,
            }

            unidade_final = unidade_da_tag
            if operation in ("sum",) and unidade_da_tag and "h" in unidade_da_tag.lower():
                unidade_final = unidade_da_tag.replace("/h", "").replace("/H", "")

            periodo_efetivo = f"{start_time} a {end_time}"
            glosa = _build_glosa(operation, method)

            output_item = {
                "tag": tag,
                "operation": operation,
                "unidade_da_tag": unidade_da_tag,
                "unidade_final_inferida": unidade_final,
                "periodo_efetivo": periodo_efetivo,
                "glosa_interpretativa": glosa,
                "quantidade_amostras": len(values),
                "result": result,
                **params_temporais,
            }

            results.append(result_item)
            outputs.append(output_item)

        return {
            "ok": True,
            "tool_name": "tag_statistics_tool",
            "tool_result": {
                "results": results,
            },
            "output": json.dumps(outputs, ensure_ascii=False),
            "answer_generation_error": None,
        }

    except _NETWORK_ERRORS as error:
        logger.warning("Math Tool /stats unreachable: %s", error)
        return {
            "ok": False,
            "tool_name": "tag_statistics_tool",
            "tool_result": {
                "endpoint": "/stats",
                "tags": tags,
                "operation": operation,
                "start_time": start_time,
                "end_time": end_time,
                "interval": interval,
                "max_count": max_count,
                "data_method": data_method,
                "summary_type": summary_type,
                "summary_duration": summary_duration,
                "calculation_basis": calculation_basis,
                "error": str(error),
            },
            "output": (
                "Serviço de estatísticas temporariamente indisponível "
                "(erro de rede). Tente novamente em instantes."
            ),
            "answer_generation_error": str(error),
        }

    except ValueError as error:
        return {
            "ok": False,
            "tool_name": "tag_statistics_tool",
            "tool_result": {
                "endpoint": "/stats",
                "tags": tags,
                "operation": operation,
                "start_time": start_time,
                "end_time": end_time,
                "interval": interval,
                "max_count": max_count,
                "data_method": data_method,
                "summary_type": summary_type,
                "summary_duration": summary_duration,
                "calculation_basis": calculation_basis,
                "error": str(error),
            },
            "output": str(error),
            "answer_generation_error": str(error),
        }

    except Exception as error:
        return {
            "ok": False,
            "tool_name": "tag_statistics_tool",
            "tool_result": {
                "endpoint": "/stats",
                "tags": tags,
                "operation": operation,
                "start_time": start_time,
                "end_time": end_time,
                "interval": interval,
                "max_count": max_count,
                "data_method": data_method,
                "summary_type": summary_type,
                "summary_duration": summary_duration,
                "calculation_basis": calculation_basis,
                "error": str(error),
            },
            "output": f"Não consegui executar a estatística de tags. Erro: {error}",
            "answer_generation_error": str(error),
        }


async def executar_calculo_historico_service(
    tags: list[str],
    operation: str,
    start_time: str,
    end_time: str = "*",
    interval: str | None = None,
    time_unit: str | None = None,
    context_text: str = "",
    max_count: int = 200000,
    data_method: str | None = "interpolated",
    summary_type: str = "Average",
    summary_duration: str = "1h",
    calculation_basis: str = "TimeWeighted",
) -> dict[str, Any]:
    outputs = []
    results = []

    try:
        method = _normalizar_data_method(data_method)

        for tag in tags:
            pi_response = await buscar_serie_pi(
                tag=tag,
                start_time=start_time,
                end_time=end_time,
                interval=interval,
                max_count=max_count,
                data_method=method,
                summary_type=summary_type,
                summary_duration=summary_duration,
                calculation_basis=calculation_basis,
            )

            points = extrair_points(pi_response)

            if len(points) < 2:
                raise ValueError(
                    f"A tag {tag} precisa de pelo menos 2 pontos válidos para calcular {operation}."
                )

            point_metadata = extrair_point_metadata(pi_response)
            unidade_da_tag = _extrair_eng_unit(point_metadata) or "sem unidade cadastrada"

            time_unit_detectado = detectar_time_unit(
                texto=context_text,
                operation=operation,
                tag=tag,
                time_unit=time_unit,
            )

            time_unit_final = inferir_time_unit_por_unidade(
                eng_unit=unidade_da_tag,
                operation=operation,
                requested_time_unit=time_unit_detectado,
            )

            payload = {
                "operation": operation,
                "time_unit": time_unit_final,
                "points": points,
            }

            result = await call_calculus(payload)
            result = _arredondar_resultado_stats(result, operation, casas=2)

            params_temporais = _parametros_temporais(
                data_method=method,
                interval=interval,
                summary_type=summary_type,
                summary_duration=summary_duration,
                calculation_basis=calculation_basis,
                max_count=max_count,
            )

            result_item = {
                "tag": tag,
                "endpoint": "/calculus",
                "payload": payload,
                "result": result,
                "unidade_da_tag": unidade_da_tag,
                "time_unit": time_unit_final,
                "time_unit_requested": time_unit,
                "time_unit_detected": time_unit_detectado,
                "quantidade_amostras": len(points),
                **params_temporais,
            }

            unidade_final = unidade_da_tag
            if operation == "integral" and unidade_da_tag and time_unit_final and time_unit_final != "none":
                unidade_final = f"{unidade_da_tag}·{time_unit_final}"
            elif operation == "derivative" and unidade_da_tag and time_unit_final and time_unit_final != "none":
                unidade_final = f"{unidade_da_tag}/{time_unit_final}"

            glosa_operation = "integral acumulada" if operation == "integral" else "taxa média de variação"
            periodo_efetivo = f"{start_time} a {end_time}"

            output_item = {
                "tag": tag,
                "operation": operation,
                "time_unit": time_unit_final,
                "time_unit_requested": time_unit,
                "time_unit_detected": time_unit_detectado,
                "unidade_da_tag": unidade_da_tag,
                "unidade_final_inferida": unidade_final,
                "periodo_efetivo": periodo_efetivo,
                "glosa_interpretativa": glosa_operation,
                "quantidade_amostras": len(points),
                "result": result,
                **params_temporais,
            }

            results.append(result_item)
            outputs.append(output_item)

        return {
            "ok": True,
            "tool_name": "tag_calculus_tool",
            "tool_result": {
                "results": results,
            },
            "output": json.dumps(outputs, ensure_ascii=False),
            "answer_generation_error": None,
        }

    except _NETWORK_ERRORS as error:
        logger.warning("Math Tool /calculus unreachable: %s", error)
        return {
            "ok": False,
            "tool_name": "tag_calculus_tool",
            "tool_result": {
                "endpoint": "/calculus",
                "tags": tags,
                "operation": operation,
                "start_time": start_time,
                "end_time": end_time,
                "interval": interval,
                "time_unit": time_unit,
                "max_count": max_count,
                "data_method": data_method,
                "summary_type": summary_type,
                "summary_duration": summary_duration,
                "calculation_basis": calculation_basis,
                "error": str(error),
            },
            "output": (
                "Serviço de cálculos temporais indisponível "
                "(erro de rede). Tente novamente em instantes."
            ),
            "answer_generation_error": str(error),
        }

    except Exception as error:
        return {
            "ok": False,
            "tool_name": "tag_calculus_tool",
            "tool_result": {
                "endpoint": "/calculus",
                "tags": tags,
                "operation": operation,
                "start_time": start_time,
                "end_time": end_time,
                "interval": interval,
                "time_unit": time_unit,
                "max_count": max_count,
                "data_method": data_method,
                "summary_type": summary_type,
                "summary_duration": summary_duration,
                "calculation_basis": calculation_basis,
                "error": str(error),
            },
            "output": f"Não consegui executar o cálculo histórico de tags. Erro: {error}",
            "answer_generation_error": str(error),
        }