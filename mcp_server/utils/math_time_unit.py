from utils.math_expression import remover_acentos


def detectar_time_unit(
    texto: str,
    operation: str,
    tag: str,
    time_unit: str | None,
) -> str:
    if time_unit and time_unit != "none":
        return time_unit

    base = remover_acentos(f"{texto or ''} {tag or ''}").lower()

    if operation == "integral":
        if (
            "potencia" in base
            or "energia" in base
            or "kw" in base
            or "kwh" in base
            or "_pot_" in base
        ):
            return "hour"

        if (
            "m/min" in base
            or "metros por minuto" in base
            or "l/min" in base
            or "litros por minuto" in base
        ):
            return "minute"

        if (
            "m3/h" in base
            or "m³/h" in base
            or "nm3/h" in base
            or "t/h" in base
            or "kg/h" in base
            or "/h" in base
            or "por hora" in base
        ):
            return "hour"

        return "hour"

    if operation == "derivative":
        if "por segundo" in base or "/s" in base:
            return "second"

        if "por hora" in base or "/h" in base:
            return "hour"

        if "por minuto" in base or "minuto" in base or "/min" in base:
            return "minute"

        return "minute"

    return "minute"