"""Política canônica de resolução de Digital Set.

Este módulo é a única fonte normativa para decidir o nome do Digital Set
de um PI Point. Todos os consumers devem utilizar ``resolve_digital_set_name``.

Ordem de resolução:
  1. Campo do point ``DigitalSetName``
  2. Campo do point ``DigitalSet``
  3. Atributo ``digitalset`` (via ``/points/{webId}/attributes?name=digitalset``)

Fontes válidas divergentes resultam em ``CONFLICT``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from domain.pims.clients.pi_web_api_client import get_digital_set_states

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lista canônica de valores inválidos (única fonte normativa)
# ---------------------------------------------------------------------------

INVALID_DIGITAL_SETS: frozenset[str] = frozenset({
    "n/a",
    "não cadastrado",
    "nao cadastrado",
    "não se aplica",
    "nao se aplica",
    "sem digital set",
    "null",
    "undefined",
    "",
})


# ---------------------------------------------------------------------------
# Fonte canônica de resolução
# ---------------------------------------------------------------------------

class DigitalSetSource(str, Enum):
    """Origem do nome do Digital Set resolvido."""

    POINT_DIGITAL_SET_NAME = "point.digital_set_name"
    POINT_DIGITAL_SET = "point.digital_set"
    ATTRIBUTE = "attribute.digitalset"
    MISSING = "missing"
    CONFLICT = "conflict"
    INVALID_RESPONSE = "invalid_response"


# ---------------------------------------------------------------------------
# Resultado da resolução
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DigitalSetResolution:
    """Resultado imutável da resolução canônica de Digital Set.

    Atributos:
        name: Nome resolvido do Digital Set (``None`` quando MISSING ou CONFLICT).
        source: Fonte de onde o nome foi obtido.
        candidates: Todos os valores não-válidos encontrados (para diagnóstico).
        is_invalid: ``True`` quando o nome resolvido é considerado inválido.
        fallback_used: ``True`` quando o atributo ``digitalset`` foi consultado.
        error_code: Code do erro quando ``source`` é ``INVALID_RESPONSE``.
        message_safe: Mensagem sanitizada (sem WebId/URL/IP).
    """

    name: str | None
    source: DigitalSetSource
    candidates: tuple[str, ...] = ()
    is_invalid: bool = False
    fallback_used: bool = False
    error_code: str | None = None
    message_safe: str | None = None


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _normalize_candidate(value: Any) -> str:
    """Normaliza um candidato sem perder o valor original."""
    if value is None:
        return ""
    return str(value).strip()


def _is_invalid_candidate(normalized: str) -> bool:
    """Verifica se o valor normalizado é um placeholder inválido."""
    return normalized in INVALID_DIGITAL_SETS


def _extract_attribute_value(
    digitalset_attribute: Mapping[str, Any] | str | None,
) -> str | None:
    """Extrai o valor do atributo ``digitalset``.

    Aceita:
    - ``str`` direto
    - ``dict`` com ``Items[0].Value``
    - ``None``
    """
    if digitalset_attribute is None:
        return None

    if isinstance(digitalset_attribute, str):
        return _normalize_candidate(digitalset_attribute) or None

    if isinstance(digitalset_attribute, Mapping):
        items = digitalset_attribute.get("Items") or []
        if isinstance(items, list) and items:
            value = items[0].get("Value")
            return _normalize_candidate(value) or None

    return None


def _text(valor: Any) -> str:
    """Mantido para compatibilidade com funções legadas."""
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar(valor: Any) -> str:
    """Mantido para compatibilidade com funções legadas."""
    return _text(valor).lower()


# ---------------------------------------------------------------------------
# API pública — compatibilidade legada
# ---------------------------------------------------------------------------

def texto(valor: Any) -> str:
    """Mantido para compatibilidade com ``tag_eh_digital`` e ``agrupar_tags_digitais_por_digital_set``."""
    return _text(valor)


def normalizar(valor: Any) -> str:
    """Mantido para compatibilidade com ``digital_set_valido``."""
    return _normalizar(valor)


def digital_set_valido(digital_set: Any) -> bool:
    """Compatibilidade legada — usa a lista canônica."""
    return _normalizar(digital_set) not in INVALID_DIGITAL_SETS


# ---------------------------------------------------------------------------
# API pública — funções legadas (mantidas para não quebrar imports)
# ---------------------------------------------------------------------------

def tag_eh_digital(tag: dict[str, Any]) -> bool:
    point_type = _normalizar(tag.get("pointType"))
    digital_set = _text(tag.get("digitalSet"))
    return point_type == "digital" and digital_set_valido(digital_set)


def agrupar_tags_digitais_por_digital_set(
    resultados_pi: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    mapa: dict[str, list[dict[str, Any]]] = {}
    for tag in resultados_pi:
        if not tag_eh_digital(tag):
            continue
        digital_set = _text(tag.get("digitalSet"))
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
        digital_set = _text(tag.get("digitalSet"))
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


# ---------------------------------------------------------------------------
# API pública — política canônica
# ---------------------------------------------------------------------------

def resolve_digital_set_name(
    *,
    point_data: Mapping[str, Any],
    digitalset_attribute: Mapping[str, Any] | str | None = None,
) -> DigitalSetResolution:
    """Política canônica de resolução do Digital Set.

    Ordem de inspeção:
      1. ``DigitalSetName`` do point
      2. ``DigitalSet`` do point
      3. Atributo ``digitalset`` (quando fornecido)

    Quando duas fontes válidas divergem (valores diferentes, ambos não-válidos),
    retorna ``CONFLICT`` com todas as fontes em ``candidates``.

    Args:
        point_data: Dicionário do PI Point (primeiro item do batch ``Items``).
        digitalset_attribute: Resultado da consulta ao atributo ``digitalset``
            (``dict`` com ``Items`` ou ``str`` direto). ``None`` quando não
            consultado.

    Returns:
        ``DigitalSetResolution`` imutável com nome, fonte, invariantes e
        metadados de diagnóstico.
    """
    fallback_used = digitalset_attribute is not None

    # --- Fonte 1: DigitalSetName ---
    raw_dsn = point_data.get("DigitalSetName")
    dsn = _normalize_candidate(raw_dsn)
    dsn_valid = not _is_invalid_candidate(dsn)

    # --- Fonte 2: DigitalSet ---
    raw_ds = point_data.get("DigitalSet")
    ds = _normalize_candidate(raw_ds)
    ds_valid = not _is_invalid_candidate(ds)

    # --- Fonte 3: Atributo ---
    attr_raw = _extract_attribute_value(digitalset_attribute)
    attr = _normalize_candidate(attr_raw) if attr_raw else ""
    attr_valid = attr_raw is not None and not _is_invalid_candidate(attr)

    # --- Coleção de candidatos não-válidos (para diagnóstico) ---
    candidates: list[str] = []
    if raw_dsn is not None and (not dsn or _is_invalid_candidate(dsn)):
        candidates.append(raw_dsn if raw_dsn is not None else "")
    if raw_ds is not None and (not ds or _is_invalid_candidate(ds)):
        candidates.append(raw_ds if raw_ds is not None else "")
    if digitalset_attribute is not None and not attr_valid:
        candidates.append(attr_raw if attr_raw else "")

    # --- Lógica de resolução ---
    if dsn_valid and ds_valid:
        # Ambos os campos do point são válidos
        if dsn.lower() == ds.lower():
            # Equivalentes — preservar grafia de DigitalSetName (prioritário)
            return DigitalSetResolution(
                name=dsn,
                source=DigitalSetSource.POINT_DIGITAL_SET_NAME,
                candidates=tuple(candidates),
                is_invalid=False,
                fallback_used=fallback_used,
            )
        else:
            # Conflito entre aliases do point
            return DigitalSetResolution(
                name=None,
                source=DigitalSetSource.CONFLICT,
                candidates=tuple(candidates),
                is_invalid=True,
                fallback_used=fallback_used,
                error_code="PI_RESPONSE_INVALID",
                message_safe="Campos DigitalSetName e DigitalSet retornaram valores incompatíveis.",
            )

    if dsn_valid:
        # Somente DigitalSetName válido
        if attr_valid and dsn.lower() != attr.lower():
            # Conflito entre point e atributo
            return DigitalSetResolution(
                name=None,
                source=DigitalSetSource.CONFLICT,
                candidates=tuple(candidates),
                is_invalid=True,
                fallback_used=fallback_used,
                error_code="PI_RESPONSE_INVALID",
                message_safe="DigitalSetName e atributo digitalset retornaram valores incompatíveis.",
            )
        return DigitalSetResolution(
            name=dsn,
            source=DigitalSetSource.POINT_DIGITAL_SET_NAME,
            candidates=tuple(candidates),
            is_invalid=False,
            fallback_used=fallback_used,
        )

    if ds_valid:
        # Somente DigitalSet válido
        if attr_valid and ds.lower() != attr.lower():
            # Conflito entre point e atributo
            return DigitalSetResolution(
                name=None,
                source=DigitalSetSource.CONFLICT,
                candidates=tuple(candidates),
                is_invalid=True,
                fallback_used=fallback_used,
                error_code="PI_RESPONSE_INVALID",
                message_safe="DigitalSet e atributo digitalset retornaram valores incompatíveis.",
            )
        return DigitalSetResolution(
            name=ds,
            source=DigitalSetSource.POINT_DIGITAL_SET,
            candidates=tuple(candidates),
            is_invalid=False,
            fallback_used=fallback_used,
        )

    if attr_valid:
        # Somente atributo válido (fallback)
        return DigitalSetResolution(
            name=attr,
            source=DigitalSetSource.ATTRIBUTE,
            candidates=tuple(candidates),
            is_invalid=False,
            fallback_used=True,
        )

    # Nenhuma fonte válida
    if digitalset_attribute is not None and attr_raw is not None and attr_raw != "" and _is_invalid_candidate(attr):
        # Atributo consultado mas retornou placeholder
        return DigitalSetResolution(
            name=None,
            source=DigitalSetSource.MISSING,
            candidates=tuple(candidates),
            is_invalid=True,
            fallback_used=True,
        )

    if digitalset_attribute is not None and attr_raw is None:
        # Atributo consultado mas retornou shape inválido
        return DigitalSetResolution(
            name=None,
            source=DigitalSetSource.INVALID_RESPONSE,
            candidates=tuple(candidates),
            is_invalid=True,
            fallback_used=True,
            error_code="PI_RESPONSE_INVALID",
            message_safe="Atributo digitalset retornou formato inesperado.",
        )

    # Nenhuma fonte consultada ou todas vazias
    return DigitalSetResolution(
        name=None,
        source=DigitalSetSource.MISSING,
        candidates=tuple(candidates),
        is_invalid=True,
        fallback_used=fallback_used,
    )
