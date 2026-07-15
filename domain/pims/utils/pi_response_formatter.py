from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


def get_attr_value(content: dict[str, Any] | None, default_value: Any = None) -> Any:
    if not content:
        return default_value

    items = content.get("Items") or []

    if len(items) > 0:
        return items[0].get("Value", default_value)

    return default_value


def formatar_data(timestamp: Any) -> str:
    if not timestamp:
        return "N/A"

    try:
        timestamp_text = str(timestamp).replace("Z", "+00:00")
        data_obj = datetime.fromisoformat(timestamp_text)

        if data_obj.tzinfo is None:
            data_obj = data_obj.replace(tzinfo=timezone.utc)

        data_sp = data_obj.astimezone(ZoneInfo("America/Sao_Paulo"))

        return data_sp.strftime("%d/%m/%Y às %H:%M:%S")

    except Exception:
        return str(timestamp)


def formatar_valor(valor: Any, engineering_units: str = "") -> str:
    if valor is None or valor == "":
        return "N/A"

    try:
        numero = float(valor)
        unidade = f" {engineering_units}" if engineering_units else ""
        return f"{numero:.2f}{unidade}"

    except (TypeError, ValueError):
        return str(valor)


def _normalizar_valor(valor: Any) -> Any:
    if isinstance(valor, dict):
        return (
            valor.get("Name")
            or valor.get("Value")
            or valor.get("ValueAsString")
            or "Erro de Leitura"
        )

    return valor


def format_pi_batch_response(raw_data: dict[str, Any]) -> dict[str, Any]:
    tags_limpas: list[dict[str, Any]] = []

    indices = set()

    for key in raw_data.keys():
        if "_" not in key:
            continue

        suffix = key.rsplit("_", 1)[-1]

        if suffix.isdigit():
            indices.add(suffix)

    for idx in sorted(indices, key=int):
        point_entry = raw_data.get(f"point_{idx}", {})
        value_entry = raw_data.get(f"value_{idx}", {})

        point_data = point_entry.get("Content") or {}
        value_data = value_entry.get("Content") or {}

        instrumenttag_data = (raw_data.get(f"instrumenttag_{idx}", {}) or {}).get("Content") or {}
        engunits_data = (raw_data.get(f"engunits_{idx}", {}) or {}).get("Content") or {}
        pointtype_data = (raw_data.get(f"pointtype_{idx}", {}) or {}).get("Content") or {}
        digitalset_data = (raw_data.get(f"digitalset_{idx}", {}) or {}).get("Content") or {}

        location1_data = (raw_data.get(f"location1_{idx}", {}) or {}).get("Content") or {}
        location2_data = (raw_data.get(f"location2_{idx}", {}) or {}).get("Content") or {}
        location3_data = (raw_data.get(f"location3_{idx}", {}) or {}).get("Content") or {}
        location4_data = (raw_data.get(f"location4_{idx}", {}) or {}).get("Content") or {}
        location5_data = (raw_data.get(f"location5_{idx}", {}) or {}).get("Content") or {}

        instrument_tag = get_attr_value(instrumenttag_data, "Não cadastrado")

        tipo_tag = (
            point_data.get("PointType")
            or get_attr_value(pointtype_data, "Não identificado")
        )

        unidade_eng = (
            point_data.get("EngUnits")
            or get_attr_value(
                engunits_data,
                value_data.get("UnitsAbbreviation") or "Sem unidade",
            )
        )

        digital_set = (
            point_data.get("DigitalSet")
            or get_attr_value(
                digitalset_data,
                "Não cadastrado"
                if str(tipo_tag).lower() == "digital"
                else "Não se aplica",
            )
        )

        valor_final = _normalizar_valor(value_data.get("Value"))

        good = value_data.get("Good")
        questionable = value_data.get("Questionable")
        substituted = value_data.get("Substituted")

        tags_limpas.append(
            {
                "nome": point_data.get("Name"),
                "descricao": point_data.get("Descriptor"),
                "instrumenttag": instrument_tag,
                "valor": valor_final,
                "data_atualizacao": value_data.get("Timestamp"),
                "good": good,
                "questionable": questionable,
                "substituted": substituted,
                "engineeringUnits": unidade_eng,
                "pointType": tipo_tag,
                "digitalSet": digital_set,
                "locations": {
                    "location1": get_attr_value(location1_data),
                    "location2": get_attr_value(location2_data),
                    "location3": get_attr_value(location3_data),
                    "location4": get_attr_value(location4_data),
                    "location5": get_attr_value(location5_data),
                },
                "digital_states_found": False,
                "digital_states": [],
            }
        )

    mensagem_final = formatar_mensagem_tags(tags_limpas)

    return {
        "resultados_pi": tags_limpas,
        "mensagem_final": mensagem_final,
    }


def _formatar_estado_digital(estado: dict[str, Any]) -> str:
    indice = estado.get("indice")
    nome = estado.get("nome")
    descricao = estado.get("descricao")

    if indice is None:
        indice = "N/A"

    if nome is None or nome == "":
        nome = "N/A"

    if descricao:
        return f"- {indice} = {nome} ({descricao})"

    return f"- {indice} = {nome}"


def _adicionar_estados_digitais(linhas: list[str], tag_data: dict[str, Any]) -> None:
    digital_states = tag_data.get("digital_states") or []
    digital_states_found = tag_data.get("digital_states_found")

    if digital_states:
        linhas.append("Digital States possíveis:")

        for estado in digital_states:
            linhas.append(_formatar_estado_digital(estado))

        return

    if digital_states_found is False:
        linhas.append("Digital States possíveis: não encontrados na PI Web API")
        return

    if digital_states_found is True:
        linhas.append("Digital States possíveis: nenhum estado retornado pela PI Web API")


def formatar_mensagem_tags(tags_limpas: list[dict[str, Any]]) -> str:
    if not tags_limpas:
        return "Nenhum dado encontrado na resposta do PI Web API."

    blocos: list[str] = []

    for tag_data in tags_limpas:
        nome = tag_data.get("nome") or "N/A"
        descricao = tag_data.get("descricao") or "N/A"
        instrumenttag = tag_data.get("instrumenttag") or ""
        valor = tag_data.get("valor")
        engineering_units = tag_data.get("engineeringUnits") or ""
        point_type = tag_data.get("pointType") or "N/A"
        digital_set = tag_data.get("digitalSet") or "N/A"

        is_digital = str(point_type).lower() == "digital"

        good = tag_data.get("good")
        questionable = tag_data.get("questionable")
        substituted = tag_data.get("substituted")

        if substituted:
            qualidade = "valor substituído pelo servidor"
        elif questionable:
            qualidade = "valor com qualidade suspeita"
        elif good is False:
            qualidade = "valor não confiável"
        elif good is True:
            qualidade = "valor confiável"
        else:
            qualidade = ""

        linhas = [
            f"Tag: {nome}",
            f"Descrição: {descricao}",
        ]

        if instrumenttag:
            linhas.append(f"InstrumentTag: {instrumenttag}")

        linhas.append(f"Tipo: {point_type}")
        linhas.append(f"Última atualização: {formatar_data(tag_data.get('data_atualizacao'))}")
        linhas.append(f"Valor: {formatar_valor(valor, engineering_units)}")

        if qualidade:
            linhas.append(f"Qualidade: {qualidade}")

        if is_digital:
            linhas.append(f"Digital set: {digital_set}")
            _adicionar_estados_digitais(linhas, tag_data)

        locations = tag_data.get("locations") or {}

        for key in ["location1", "location2", "location3", "location4", "location5"]:
            value = locations.get(key)

            if value not in [None, ""]:
                linhas.append(f"{key.capitalize()}: {value}")

        blocos.append("\n".join(linhas))

    return "\n\n".join(blocos)