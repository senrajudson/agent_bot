from __future__ import annotations

from typing import Any, Final

import httpx

from domain.pims.clients.pi_web_api_client import get_point_attributes

_VALID_GROUPS: Final[frozenset[str]] = frozenset({
    "auto", "compression", "exception", "archive",
    "identity", "scaling", "interface", "security", "all",
})

_ALIASES: Final[dict[str, str]] = {
    # compression
    "compressao": "compression",
    "compressão": "compression",
    "compdev": "compression",
    "compmax": "compression",
    # exception
    "excecao": "exception",
    "exceção": "exception",
    "excesso": "exception",
    "excesso": "exception",
    "excessao": "exception",
    "excessão": "exception",
    "exececao": "exception",
    "execeção": "exception",
    "excdev": "exception",
    "excmax": "exception",
    # archive
    "arquivamento": "archive",
    "archiving": "archive",
    "scan": "archive",
    # identity
    "metadata": "identity",
    "identidade": "identity",
    "descricao": "identity",
    "descrição": "identity",
    "unidade": "identity",
    "pointsource": "identity",
    "instrumenttag": "identity",
    # scaling
    "escala": "scaling",
    "zero": "scaling",
    "span": "scaling",
    "typicalvalue": "scaling",
    # interface
    "location": "interface",
    "sourcetag": "interface",
    # security
    "seguranca": "security",
    "segurança": "security",
}

_GROUP_ATTRIBUTES: Final[dict[str, frozenset[str]]] = {
    "auto": frozenset({
        "compressing", "compdev", "compdevpercent", "compmin", "compmax",
        "excdev", "excdevpercent", "excmin", "excmax",
        "scan", "pointsource", "instrumenttag",
    }),
    "compression": frozenset({
        "compressing", "compdev", "compdevpercent", "compmin", "compmax",
    }),
    "exception": frozenset({
        "excdev", "excdevpercent", "excmin", "excmax",
    }),
    "archive": frozenset({
        "archiving", "scan", "shutdown", "step", "future",
    }),
    "identity": frozenset({
        "tag", "descriptor", "engunits", "pointtype",
        "pointsource", "instrumenttag", "digitalset",
    }),
    "scaling": frozenset({
        "zero", "span", "typicalvalue", "displaydigits",
        "squareroot", "convers",
    }),
    "interface": frozenset({
        "location1", "location2", "location3", "location4", "location5",
        "exdesc", "sourcetag", "srcptid",
    }),
    "security": frozenset({
        "ptsecurity", "datasecurity", "ptaccess", "dataaccess",
        "ptowner", "ptgroup", "dataowner", "datagroup",
    }),
}


def _validar_tag(tag: str) -> str:
    tag = str(tag or "").strip()
    if not tag:
        raise ValueError("Tag vazia ou inválida.")
    return tag


def _resolve_group(group: str) -> str:
    group = str(group or "").strip().lower()
    if not group:
        raise ValueError("Grupo não informado.")

    resolved = _ALIASES.get(group, group)

    if resolved not in _VALID_GROUPS:
        valid = sorted(_VALID_GROUPS)
        aliases = sorted(_ALIASES.keys())
        raise ValueError(
            f"Grupo '{group}' inválido. Grupos válidos: {', '.join(valid)}. "
            f"Aliases aceitos: {', '.join(aliases)}."
        )

    return resolved


def _items_to_dict(items: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        name = str(item.get("Name", "")).strip().lower()
        if not name or name in ("links",):
            continue
        result[name] = item.get("Value")
    return result


def _filter_by_names(
    attr_dict: dict[str, Any],
    names: list[str],
) -> tuple[dict[str, Any], list[str]]:
    normalized = {n.strip().lower() for n in names if n.strip()}
    found: dict[str, Any] = {}
    missing: list[str] = []
    for name in sorted(normalized):
        if name in attr_dict:
            found[name] = attr_dict[name]
        else:
            missing.append(name)
    return found, missing


def _interpret_value(name: str, value: Any) -> str:
    if value is None:
        return "(não configurado)"

    if isinstance(value, str) and not value.strip():
        return "(vazio)"

    if name in ("compressing", "archiving", "shutdown"):
        return "ativada" if value == 1 or str(value) == "1" else "desativada"

    if name == "scan":
        return "ligado" if value == 1 or str(value) == "1" else "desligado"

    if name == "step":
        return "degrau" if value == 1 or str(value) == "1" else "contínuo"

    if name in ("future",):
        return "sim" if value == 1 or str(value) == "1" else "não"

    if name in ("compmin", "compmax", "excmin", "excmax", "compdev", "excdev"):
        try:
            num = float(value)
            return f"{num} segundos"
        except (ValueError, TypeError):
            return str(value)

    if name in ("compdevpercent", "excdevpercent"):
        try:
            num = float(value)
            return f"{num} %"
        except (ValueError, TypeError):
            return str(value)

    return str(value)


def _format_output(
    tag: str,
    attr_dict: dict[str, Any],
    missing: list[str],
) -> str:
    lines: list[str] = [f"Atributos da tag {tag}:"]

    for name in sorted(attr_dict):
        raw = attr_dict[name]
        interpreted = _interpret_value(name, raw)
        lines.append(f"- {name}: {interpreted}")

    for name in sorted(missing):
        lines.append(f"- {name}: (não configurado)")

    return "\n".join(lines)


async def get_tag_attributes(
    tag: str,
    attribute_group: str = "auto",
    attributes: list[str] | None = None,
) -> dict[str, Any]:
    tag = _validar_tag(tag)

    if attributes:
        resolved_group = attribute_group
        filtro = None
    else:
        resolved_group = _resolve_group(attribute_group)
        filtro = resolved_group

    try:
        raw = await get_point_attributes(tag)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            msg = f"Tag {tag} não encontrada no PI Server."
            return {
                "ok": False, "tag": tag, "attribute_group": resolved_group,
                "count": 0, "attributes": {}, "missing_attributes": [],
                "message": msg, "output": msg,
            }
        raise

    items = raw.get("Items") or []
    attr_dict = _items_to_dict(items)

    if not attr_dict:
        msg = f"Nenhum atributo retornado pela PI Web API para a tag {tag}."
        return {
            "ok": False, "tag": tag, "attribute_group": resolved_group,
            "count": 0, "attributes": {}, "missing_attributes": [],
            "message": msg, "output": msg,
        }

    if attributes:
        filtered, missing = _filter_by_names(attr_dict, attributes)
    elif filtro == "all" or filtro is None:
        filtered = attr_dict
        missing: list[str] = []
    else:
        expected = _GROUP_ATTRIBUTES.get(filtro, frozenset())
        filtered, missing = _filter_by_names(attr_dict, list(expected))

    output = _format_output(tag, filtered, missing)
    return {
        "ok": True, "tag": tag, "attribute_group": resolved_group,
        "count": len(filtered), "attributes": filtered,
        "missing_attributes": missing,
        "message": f"{len(filtered)} atributo(s) encontrado(s).",
        "output": output,
    }
