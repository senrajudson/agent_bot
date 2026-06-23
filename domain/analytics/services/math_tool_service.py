from __future__ import annotations

import json
import logging
import socket
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

            output_item = {
                "tag": tag,
                "operation": operation,
                "unidade_da_tag": unidade_da_tag,
                "observacao_unidade": (
                    "Nunca use 'unidade_da_tag na resposta final. "
                    "Você precisa inferir a unidade baseando-se na operação "
                    "feita. Não explique como você inferiu. Não explique "
                    "qual o cálculo feito."
                ),
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

            output_item = {
                "tag": tag,
                "operation": operation,
                "time_unit": time_unit_final,
                "time_unit_requested": time_unit,
                "time_unit_detected": time_unit_detectado,
                "unidade_da_tag": unidade_da_tag,
                "observacao_unidade": (
                    "Nunca use 'unidade_da_tag na resposta final. "
                    "Você precisa inferir a unidade baseando-se na operação "
                    "feita. Não explique como você inferiu. Não explique "
                    "qual o cálculo feito."
                ),
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