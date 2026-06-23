from typing import Any

from domain.pims.clients.pi_web_api_client import get_digital_set_states


INVALID_DIGITAL_SETS = {
    "n/a",
    "não cadastrado",
    "nao cadastrado",
    "não se aplica",
    "nao se aplica",
    "sem digital set",
    "null",
    "undefined",
    "",
}


def texto(valor: Any) -> str:
    if valor is None:
        return ""

    return str(valor).strip()


def normalizar(valor: Any) -> str:
    return texto(valor).lower()


def digital_set_valido(digital_set: Any) -> bool:
    return normalizar(digital_set) not in INVALID_DIGITAL_SETS


def tag_eh_digital(tag: dict[str, Any]) -> bool:
    point_type = normalizar(tag.get("pointType"))
    digital_set = texto(tag.get("digitalSet"))

    return point_type == "digital" and digital_set_valido(digital_set)


def agrupar_tags_digitais_por_digital_set(
    resultados_pi: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    mapa: dict[str, list[dict[str, Any]]] = {}

    for tag in resultados_pi:
        if not tag_eh_digital(tag):
            continue

        digital_set = texto(tag.get("digitalSet"))

        if digital_set not in mapa:
            mapa[digital_set] = []

        mapa[digital_set].append(tag)

    return mapa


async def enriquecer_com_digital_states(
    resultados_pi: list[dict[str, Any]],
) -> dict[str, Any]:
    mapa_digital_sets = agrupar_tags_digitais_por_digital_set(resultados_pi)

    digital_states_por_set: dict[str, Any] = {}

    for digital_set in mapa_digital_sets.keys():
        digital_states_por_set[digital_set] = await get_digital_set_states(digital_set)

    for tag in resultados_pi:
        digital_set = texto(tag.get("digitalSet"))

        if digital_set in digital_states_por_set:
            info = digital_states_por_set[digital_set]

            tag["digital_states_found"] = info.get("found", False)
            tag["digital_states"] = info.get("states", [])
        else:
            tag["digital_states_found"] = False
            tag["digital_states"] = []

    return {
        "tem_tag_digital": len(mapa_digital_sets) > 0,
        "qtd_tags_digitais": sum(len(tags) for tags in mapa_digital_sets.values()),
        "qtd_digital_sets": len(mapa_digital_sets),
        "digital_sets_consultados": list(mapa_digital_sets.keys()),
        "digital_states_por_set": digital_states_por_set,
        "resultados_pi": resultados_pi,
    }