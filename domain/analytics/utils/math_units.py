def normalizar_unidade(unidade: str | None) -> str:
    if not unidade:
        return ""

    return str(unidade).strip()


def inferir_time_unit_por_unidade(
    eng_unit: str | None,
    operation: str,
    requested_time_unit: str | None = None,
) -> str:
    unit = normalizar_unidade(eng_unit).lower()

    if operation == "integral":
        if "/h" in unit or "/hr" in unit or "por hora" in unit:
            return "hour"

        if "/min" in unit or "por minuto" in unit:
            return "minute"

        if "/s" in unit or "por segundo" in unit:
            return "second"

        if requested_time_unit and requested_time_unit != "none":
            return requested_time_unit

        return "hour"

    if operation == "derivative":
        if requested_time_unit and requested_time_unit != "none":
            return requested_time_unit

        return "minute"

    return requested_time_unit or "none"
