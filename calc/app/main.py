from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
import statistics
import math
import ast
import operator


app = FastAPI(
    title="Math Tool",
    description="Ferramenta local para estatística, cálculo aritmético e cálculo temporal.",
    version="2.0.0"
)


class StatsRequest(BaseModel):
    values: List[float] = Field(..., description="Lista de valores numéricos.")
    operations: Optional[List[str]] = Field(
        default=None,
        description="Operações estatísticas desejadas."
    )


class CalculateRequest(BaseModel):
    expression: str = Field(..., description="Expressão aritmética simples.")


class TimePoint(BaseModel):
    timestamp: Union[str, datetime]
    value: float


class CalculusRequest(BaseModel):
    operation: str = Field(
        ...,
        description="Operação temporal: integral ou derivative."
    )
    time_unit: Optional[str] = Field(
        default="second",
        description="Unidade de tempo: second, minute ou hour."
    )
    points: List[TimePoint] = Field(
        ...,
        description="Lista de pontos com timestamp e value."
    )


def validate_values(values: List[float]) -> List[float]:
    if not values:
        raise ValueError("A lista de valores não pode estar vazia.")

    if len(values) > 100000:
        raise ValueError("A lista de valores é muito grande. Limite: 100000 valores.")

    clean_values = []

    for value in values:
        if not isinstance(value, (int, float)):
            raise ValueError("Todos os valores precisam ser numéricos.")

        if not math.isfinite(value):
            raise ValueError("A lista contém valor inválido, infinito ou NaN.")

        clean_values.append(float(value))

    return clean_values


def calculate_stats(values: List[float], operations: Optional[List[str]]) -> Dict[str, Any]:
    values = validate_values(values)

    available_operations = {
        "count",
        "sum",
        "mean",
        "median",
        "min",
        "max",
        "range",
        "variance_population",
        "variance_sample",
        "stddev_population",
        "stddev_sample"
    }

    if operations is None or len(operations) == 0:
        operations = sorted(list(available_operations))

    invalid_operations = [op for op in operations if op not in available_operations]

    if invalid_operations:
        raise ValueError(f"Operações inválidas: {invalid_operations}")

    result = {}

    if "count" in operations:
        result["count"] = len(values)

    if "sum" in operations:
        result["sum"] = sum(values)

    if "mean" in operations:
        result["mean"] = statistics.mean(values)

    if "median" in operations:
        result["median"] = statistics.median(values)

    if "min" in operations:
        result["min"] = min(values)

    if "max" in operations:
        result["max"] = max(values)

    if "range" in operations:
        result["range"] = max(values) - min(values)

    if "variance_population" in operations:
        result["variance_population"] = statistics.pvariance(values)

    if "stddev_population" in operations:
        result["stddev_population"] = statistics.pstdev(values)

    if "variance_sample" in operations:
        result["variance_sample"] = statistics.variance(values) if len(values) > 1 else None

    if "stddev_sample" in operations:
        result["stddev_sample"] = statistics.stdev(values) if len(values) > 1 else None

    return result


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "ln": math.log,
    "exp": math.exp,
}


ALLOWED_NAMES = {
    "pi": math.pi,
    "e": math.e,
}


def safe_eval_expression(expression: str) -> float:
    expression = str(expression or "").strip().replace("^", "**")

    if not expression:
        raise ValueError("Expressão vazia.")

    if len(expression) > 500:
        raise ValueError("Expressão muito longa. Limite: 500 caracteres.")

    tree = ast.parse(expression, mode="eval")

    def eval_node(node):
        if isinstance(node, ast.Expression):
            return eval_node(node.body)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError("A expressão contém valor inválido.")

        if isinstance(node, ast.Num):
            return float(node.n)

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)

            if op_type not in ALLOWED_OPERATORS:
                raise ValueError("Operador não permitido.")

            left = eval_node(node.left)
            right = eval_node(node.right)

            return ALLOWED_OPERATORS[op_type](left, right)

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)

            if op_type not in ALLOWED_OPERATORS:
                raise ValueError("Operador unário não permitido.")

            return ALLOWED_OPERATORS[op_type](eval_node(node.operand))

        if isinstance(node, ast.Name):
            if node.id in ALLOWED_NAMES:
                return ALLOWED_NAMES[node.id]

            raise ValueError(f"Nome não permitido na expressão: {node.id}")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Função inválida.")

            function_name = node.func.id

            if function_name not in ALLOWED_FUNCTIONS:
                raise ValueError(f"Função não permitida: {function_name}")

            if node.keywords:
                raise ValueError("Argumentos nomeados não são permitidos.")

            args = [eval_node(arg) for arg in node.args]

            return ALLOWED_FUNCTIONS[function_name](*args)

        raise ValueError("Expressão contém elemento não permitido.")

    result = eval_node(tree)

    if not isinstance(result, (int, float)) or not math.isfinite(result):
        raise ValueError("Resultado inválido, infinito ou NaN.")

    return float(result)


def parse_timestamp(timestamp: Union[str, datetime]) -> datetime:
    if isinstance(timestamp, datetime):
        dt = timestamp
    else:
        text = str(timestamp).strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def get_time_unit_seconds(time_unit: Optional[str]) -> float:
    unit = str(time_unit or "second").strip().lower()

    aliases = {
        "s": "second",
        "sec": "second",
        "second": "second",
        "seconds": "second",
        "m": "minute",
        "min": "minute",
        "minute": "minute",
        "minutes": "minute",
        "h": "hour",
        "hr": "hour",
        "hour": "hour",
        "hours": "hour",
    }

    unit = aliases.get(unit, unit)

    if unit == "second":
        return 1.0

    if unit == "minute":
        return 60.0

    if unit == "hour":
        return 3600.0

    raise ValueError("time_unit inválido. Use second, minute ou hour.")


def validate_points(points: List[TimePoint]) -> List[Dict[str, Any]]:
    if not points:
        raise ValueError("A lista de pontos não pode estar vazia.")

    if len(points) > 100000:
        raise ValueError("A lista de pontos é muito grande. Limite: 100000 pontos.")

    clean_points = []

    for point in points:
        value = float(point.value)

        if not math.isfinite(value):
            raise ValueError("A lista contém valor inválido, infinito ou NaN.")

        clean_points.append({
            "timestamp": parse_timestamp(point.timestamp),
            "value": value
        })

    clean_points.sort(key=lambda item: item["timestamp"])

    if len(clean_points) < 2:
        raise ValueError("São necessários pelo menos 2 pontos para integral ou derivada temporal.")

    return clean_points


def calculate_timeseries_integral(points: List[TimePoint], time_unit: Optional[str]) -> Dict[str, Any]:
    clean_points = validate_points(points)
    unit_seconds = get_time_unit_seconds(time_unit)

    integral = 0.0
    valid_intervals = 0

    for current_point, next_point in zip(clean_points, clean_points[1:]):
        dt_seconds = (next_point["timestamp"] - current_point["timestamp"]).total_seconds()

        if dt_seconds <= 0:
            continue

        dt_unit = dt_seconds / unit_seconds
        average_value = (current_point["value"] + next_point["value"]) / 2

        integral += average_value * dt_unit
        valid_intervals += 1

    if valid_intervals == 0:
        raise ValueError("Não há intervalos de tempo válidos para calcular a integral.")

    duration_seconds = (clean_points[-1]["timestamp"] - clean_points[0]["timestamp"]).total_seconds()

    return {
        "operation": "integral",
        "method": "trapezoidal",
        "time_unit": time_unit,
        "input_count": len(clean_points),
        "interval_count": valid_intervals,
        "start_timestamp": clean_points[0]["timestamp"].isoformat(),
        "end_timestamp": clean_points[-1]["timestamp"].isoformat(),
        "duration_seconds": duration_seconds,
        "duration_in_time_unit": duration_seconds / unit_seconds,
        "integral": integral
    }


def calculate_timeseries_derivative(points: List[TimePoint], time_unit: Optional[str]) -> Dict[str, Any]:
    clean_points = validate_points(points)
    unit_seconds = get_time_unit_seconds(time_unit)

    derivatives = []

    for current_point, next_point in zip(clean_points, clean_points[1:]):
        dt_seconds = (next_point["timestamp"] - current_point["timestamp"]).total_seconds()

        if dt_seconds <= 0:
            continue

        dt_unit = dt_seconds / unit_seconds
        derivative = (next_point["value"] - current_point["value"]) / dt_unit

        derivatives.append(derivative)

    if not derivatives:
        raise ValueError("Não há intervalos de tempo válidos para calcular a derivada.")

    total_duration_seconds = (clean_points[-1]["timestamp"] - clean_points[0]["timestamp"]).total_seconds()

    if total_duration_seconds <= 0:
        raise ValueError("Duração total inválida para calcular derivada.")

    total_duration_unit = total_duration_seconds / unit_seconds
    total_change = clean_points[-1]["value"] - clean_points[0]["value"]
    average_derivative = total_change / total_duration_unit

    return {
        "operation": "derivative",
        "method": "finite_difference",
        "time_unit": time_unit,
        "input_count": len(clean_points),
        "interval_count": len(derivatives),
        "start_timestamp": clean_points[0]["timestamp"].isoformat(),
        "end_timestamp": clean_points[-1]["timestamp"].isoformat(),
        "start_value": clean_points[0]["value"],
        "end_value": clean_points[-1]["value"],
        "value_change": total_change,
        "duration_seconds": total_duration_seconds,
        "duration_in_time_unit": total_duration_unit,
        "average_derivative": average_derivative,
        "min_derivative": min(derivatives),
        "max_derivative": max(derivatives),
        "first_interval_derivative": derivatives[0],
        "last_interval_derivative": derivatives[-1]
    }


def calculate_calculus(request: CalculusRequest) -> Dict[str, Any]:
    operation = str(request.operation or "").strip().lower()

    if operation == "integral":
        return calculate_timeseries_integral(request.points, request.time_unit)

    if operation == "derivative":
        return calculate_timeseries_derivative(request.points, request.time_unit)

    raise ValueError("Operação inválida para cálculo temporal. Use integral ou derivative.")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "math_tool",
        "version": "2.0.0"
    }


@app.post("/stats")
def stats(request: StatsRequest):
    try:
        result = calculate_stats(request.values, request.operations)

        return {
            "ok": True,
            "input_count": len(request.values),
            "operations": request.operations,
            "result": result
        }

    except Exception as error:
        return {
            "ok": False,
            "error": str(error)
        }


@app.post("/calculate")
def calculate(request: CalculateRequest):
    try:
        result = safe_eval_expression(request.expression)

        return {
            "ok": True,
            "expression": request.expression,
            "result": {
                "calculate": result
            }
        }

    except Exception as error:
        return {
            "ok": False,
            "error": str(error)
        }


@app.post("/calculus")
def calculus(request: CalculusRequest):
    try:
        result = calculate_calculus(request)

        return {
            "ok": True,
            "input_count": len(request.points),
            "operation": request.operation,
            "time_unit": request.time_unit,
            "result": result
        }

    except Exception as error:
        return {
            "ok": False,
            "error": str(error)
        }