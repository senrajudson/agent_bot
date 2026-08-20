from __future__ import annotations
import asyncio
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Literal

import httpx

from domain.core.config import get_domain_settings
from domain.pims.clients.pi_web_api_client import (
    POINT_SELECTED_FIELDS,
    SEARCH_SELECTED_FIELDS,
    get_points_by_name_filter,
    search_pi_points as client_search,
)

import logging

logger = logging.getLogger(__name__)

_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
)

VALID_SEARCH_MODES = {"auto", "name", "description", "query"}
_DEFAULT_MAX_COUNT = 15
_MAX_COUNT_HARD_CAP = 15
_MAX_QUERY_LENGTH = 200


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


MatchBasis = Literal[
    "name_exact",
    "name_contains_all_tokens",
    "name_contains_context_token",
    "name_contains_variable_token",
    "description_contains_all_tokens",
    "description_contains_variable_token",
    "industrial_code_match",
    "technical_expansion_match",
]

# ---------------------------------------------------------------------------
# Query Understanding — domain model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchTerms:
    original: str
    normalized_phrase: str
    tokens: list[str]
    variable_terms: list[str]
    equipment_terms: list[str]
    area_terms: list[str]
    technical_terms: list[str]

# ---------------------------------------------------------------------------
# Query Understanding — stopwords, dictionaries, helpers
# ---------------------------------------------------------------------------

_STOPWORDS: set[str] = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
    "por", "para", "pelo", "pela", "com", "sem", "sob", "sobre",
    "e", "ou", "mas", "que", "se", "é", "foi", "ser", "estar",
    "tem", "ter", "há", "haver", "existe", "existem", "haveria",
    "algum", "alguma", "alguns", "algumas", "todo", "toda", "todos", "todas",
    "muito", "muita", "pouco", "pouca", "mais", "menos", "qual", "quais",
    "como", "aqui", "ali", "lá", "onde", "quando", "porque",
    "eu", "tu", "ele", "ela", "nós", "vós", "eles", "elas",
    "meu", "minha", "teu", "tua", "seu", "sua", "nosso", "nossa",
    "este", "esta", "isto", "esse", "essa", "isso", "aquele", "aquela", "aquilo",
    "tal", "tais", "certo", "certa", "apenas", "só", "somente",
    "tag", "tags",
    "procure", "procura", "procurar", "buscar", "localizar", "encontrar",
    "lista", "listar", "mostra", "mostrar", "retorna", "retornar", "retorne",
    "me", "te", "se", "lhe", "nos", "vos",
    "pode", "poderia", "poder", "gostaria", "queria", "quero",
    "sobre", "ainda", "já", "também", "bem", "sempre",
    "relacionada", "relacionado", "referente",
}

_VARIABLE_DICT: dict[str, list[str]] = {
    "velocidade": ["VEL", "VELOC", "VELOCIDADE"],
    "temperatura": ["TEMP", "TEMPER", "TEMPERATURA"],
    "pressao": ["PRESS", "PRESSAO", "PSI", "BAR"],
    "vazao": ["VAZ", "VAZAO", "FLOW"],
    "nivel": ["NIV", "NIVEL", "LEVEL"],
    "corrente": ["CORR", "CORRENTE", "AMP", "AMPER"],
    "tensao": ["TENS", "TENSAO", "VOLT"],
    "potencia": ["POT", "POTEN", "POTENCIA", "KW", "HP"],
    "vibracao": ["VIBR", "VIBRAC", "VIBRACAO"],
    "torque": ["TORQ", "TORQUE"],
    "umidade": ["UMID", "UMIDADE"],
    "ph": ["PH"],
}

_EQUIPMENT_DICT: dict[str, list[str]] = {
    "forno": ["FRN", "FORNO"],
    "bomba": ["BBA", "BOMBA", "BOMB"],
    "compressor": ["COMP", "COMPR", "COMPRESSOR"],
    "tambor": ["TBR", "TAMBOR", "TAMB"],
    "cilindro": ["CIL", "CILIN", "CILINDRO"],
    "valvula": ["VLV", "VALV", "VALVULA"],
    "tanque": ["TQ", "TANQ", "TANQUE"],
    "pistao": ["PIST", "PISTAO", "PST"],
    "esteira": ["EST", "ESTEIRA"],
    "cooler": ["COOL", "COOLER", "RESFRIADOR"],
}

_AREA_DICT: dict[str, list[str]] = {
    "aciaria": ["ACI", "ACIA"],
    "laminacao": ["LFI", "LFS", "LAM"],
    "coqueria": ["COQ", "COQ1", "COQ2"],
    "sin": ["SIN", "SINTER"],
    "cdt": ["CDT", "CD"],
}

_INDUSTRIAL_CODE_REGEX = re.compile(r"^[A-Z0-9]{2,4}$", re.IGNORECASE)

_ACCENT_MAP = str.maketrans({
    "á": "a", "à": "a", "ã": "a", "â": "a",
    "é": "e", "ê": "e", "è": "e",
    "í": "i", "ì": "i", "î": "i",
    "ó": "o", "ò": "o", "õ": "o", "ô": "o",
    "ú": "u", "ù": "u", "û": "u",
    "ç": "c",
    "ü": "u",
})


def _normalize_accent(text: str) -> str:
    return text.translate(_ACCENT_MAP)


def _extract_search_terms(query: str) -> SearchTerms:
    original = query.strip()
    lower = original.lower()
    raw_tokens = re.findall(r"\w+", lower)

    meaningful: list[str] = []
    for t in raw_tokens:
        t_norm = _normalize_accent(t)
        if t_norm in _STOPWORDS:
            continue
        if _useful_chars(t) < 2:
            continue
        meaningful.append(t_norm)

    normalized_phrase = " ".join(meaningful)

    variable_terms: list[str] = []
    equipment_terms: list[str] = []
    area_terms: list[str] = []

    for t in meaningful:
        if t in _VARIABLE_DICT:
            variable_terms.append(t)
        elif t in _EQUIPMENT_DICT:
            equipment_terms.append(t)
        elif t in _AREA_DICT or _INDUSTRIAL_CODE_REGEX.match(t):
            area_terms.append(t)

    technical_terms: list[str] = list(meaningful)
    for t in meaningful:
        if t in _VARIABLE_DICT:
            technical_terms.extend(_VARIABLE_DICT[t])
        if t in _EQUIPMENT_DICT:
            technical_terms.extend(_EQUIPMENT_DICT[t])
        if t in _AREA_DICT:
            technical_terms.extend(_AREA_DICT[t])

    seen: set[str] = set()
    technical_terms = [x for x in technical_terms if not (x in seen or seen.add(x))]

    return SearchTerms(
        original=original,
        normalized_phrase=normalized_phrase,
        tokens=meaningful,
        variable_terms=variable_terms,
        equipment_terms=equipment_terms,
        area_terms=area_terms,
        technical_terms=technical_terms,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _useful_chars(text: str) -> int:
    return len(re.sub(r"[\s*?]", "", text or ""))


def _sanitize_query(query: str) -> str | None:
    if not query or not query.strip():
        return None
    sanitized = query.strip()
    if len(sanitized) > _MAX_QUERY_LENGTH:
        sanitized = sanitized[:_MAX_QUERY_LENGTH]
    if _useful_chars(sanitized) < 2:
        return None
    return sanitized


def _validate_max_count(max_count: int) -> int:
    if max_count < 1:
        return _DEFAULT_MAX_COUNT
    return min(max_count, _MAX_COUNT_HARD_CAP)


def _tokenize_query(query: str) -> list[str]:
    return _extract_search_terms(query).tokens


# ---------------------------------------------------------------------------
# Description variants builder
# ---------------------------------------------------------------------------

def _build_description_variants(search_terms: SearchTerms) -> list[str]:
    variants: list[str] = []
    tokens = search_terms.tokens
    if len(tokens) >= 2:
        variants.append(f'Description:="*{search_terms.original}*"')
        variants.append(f'Description:="*{search_terms.normalized_phrase}*"')
        variants.append(f"Description:=*{'*'.join(tokens)}*")
        variants.append(f"Description:=*{tokens[0]}*")
        variants.append(f"Description:=*{tokens[1]}*")
    elif len(tokens) == 1:
        variants.append(f"Description:=*{tokens[0]}*")
    seen: set[str] = set()
    return [v for v in variants if not (v in seen or seen.add(v))]


# ---------------------------------------------------------------------------
# Name variants builder — combos first, then individuals
# ---------------------------------------------------------------------------

def _build_name_variants(search_terms: SearchTerms | None = None) -> list[str]:
    variants: list[str] = []
    if search_terms is None:
        return variants

    query = search_terms.original
    # Use original query tokens for case preservation in Name search
    query_tokens = [t for t in re.findall(r"\w+", query) if _useful_chars(t) >= 2]
    if not query_tokens:
        return variants

    if len(query_tokens) >= 2:
        variants.append(f'Name:="*{query}*"')
        variants.append(f'Name:="*{search_terms.normalized_phrase}*"')
        variants.append(f"Name:=*{'*'.join(query_tokens)}*")

        # Combinations: variable × equipment (priority)
        if search_terms.variable_terms and search_terms.equipment_terms:
            for v in search_terms.variable_terms:
                for e in search_terms.equipment_terms:
                    for ev in _VARIABLE_DICT.get(v, [v]):
                        for ee in _EQUIPMENT_DICT.get(e, [e]):
                            variants.append(f"Name:=*{ev}*{ee}*")
                            variants.append(f"Name:=*{ee}*{ev}*")

        # Combinations: area/code × variable/equipment
        if search_terms.area_terms:
            for a in search_terms.area_terms:
                for v in search_terms.variable_terms:
                    for ev in _VARIABLE_DICT.get(v, [v]):
                        variants.append(f"Name:=*{a.upper()}*{ev}*")
                        variants.append(f"Name:=*{ev}*{a.upper()}*")
                for e in search_terms.equipment_terms:
                    for ee in _EQUIPMENT_DICT.get(e, [e]):
                        variants.append(f"Name:=*{a.upper()}*{ee}*")
                        variants.append(f"Name:=*{ee}*{a.upper()}*")

        # Individual terms (using original-case tokens)
        variants.append(f"Name:=*{query_tokens[0]}*")
        variants.append(f"Name:=*{query_tokens[1]}*")

        # Technical expansions (uppercase, ≥3 chars)
        if search_terms.technical_terms:
            token_upper = {t.upper() for t in query_tokens}
            for t in search_terms.technical_terms:
                if t.isupper() and len(t) >= 3 and t not in token_upper:
                    variants.append(f"Name:=*{t}*")

    elif len(query_tokens) == 1:
        variants.append(f"Name:=*{query_tokens[0]}*")
        if search_terms.technical_terms:
            token_upper = query_tokens[0].upper()
            for t in search_terms.technical_terms:
                if t.isupper() and len(t) >= 3 and t != token_upper:
                    variants.append(f"Name:=*{t}*")

    seen: set[str] = set()
    return [v for v in variants if not (v in seen or seen.add(v))]


# ---------------------------------------------------------------------------
# nameFilter variants builder — same priority (combos first)
# ---------------------------------------------------------------------------

def _build_namefilter_variants(search_terms: SearchTerms | None = None) -> list[str]:
    variants: list[str] = []
    if search_terms is None:
        return variants

    # Use original query tokens for case preservation
    query = search_terms.original
    query_tokens = [t for t in re.findall(r"\w+", query) if _useful_chars(t) >= 2]
    if not query_tokens:
        return variants

    if len(query_tokens) >= 2:
        variants.append(f"*{'*'.join(query_tokens)}*")

        # Combinations: variable × equipment
        if search_terms.variable_terms and search_terms.equipment_terms:
            for v in search_terms.variable_terms:
                for e in search_terms.equipment_terms:
                    for ev in _VARIABLE_DICT.get(v, [v]):
                        for ee in _EQUIPMENT_DICT.get(e, [e]):
                            variants.append(f"*{ev}*{ee}*")
                            variants.append(f"*{ee}*{ev}*")

        # Combinations: area/code × variable/equipment
        if search_terms.area_terms:
            for a in search_terms.area_terms:
                for v in search_terms.variable_terms:
                    for ev in _VARIABLE_DICT.get(v, [v]):
                        variants.append(f"*{a.upper()}*{ev}*")
                        variants.append(f"*{ev}*{a.upper()}*")
                for e in search_terms.equipment_terms:
                    for ee in _EQUIPMENT_DICT.get(e, [e]):
                        variants.append(f"*{a.upper()}*{ee}*")
                        variants.append(f"*{ee}*{a.upper()}*")

        # Individual terms (using original-case tokens)
        variants.append(f"*{query_tokens[0]}*")
        variants.append(f"*{query_tokens[1]}*")

        # Technical expansions
        if search_terms.technical_terms:
            token_upper = {t.upper() for t in query_tokens}
            for t in search_terms.technical_terms:
                if t.isupper() and len(t) >= 3 and t not in token_upper:
                    variants.append(f"*{t}*")

    elif len(query_tokens) == 1:
        variants.append(f"*{query_tokens[0]}*")
        if search_terms.technical_terms:
            token_upper = query_tokens[0].upper()
            for t in search_terms.technical_terms:
                if t.isupper() and len(t) >= 3 and t != token_upper:
                    variants.append(f"*{t}*")

    seen: set[str] = set()
    return [v for v in variants if not (v in seen or seen.add(v))]


# ---------------------------------------------------------------------------
# Parallel query executor (strict AND)
# ---------------------------------------------------------------------------

async def _run_single_query(query_str: str, max_count: int, timeout: float) -> list[dict[str, Any]]:
    try:
        raw = await asyncio.wait_for(
            client_search(
                query=query_str,
                max_count=max_count,
                selected_fields=SEARCH_SELECTED_FIELDS,
            ),
            timeout=timeout,
        )
        return _format_items(raw)
    except asyncio.TimeoutError:
        logger.warning("Query timeout: query=%s", query_str)
        return []
    except httpx.HTTPStatusError as exc:
        logger.warning("Query HTTP %d: query=%s", exc.response.status_code, query_str)
        return []
    except _NETWORK_ERRORS:
        logger.warning("Query unreachable: query=%s", query_str)
        return []
    except Exception as exc:
        logger.warning("Query error: query=%s exc=%s", query_str, exc)
        return []


async def _parallel_search(
    queries: list[str],
    max_count: int,
    timeout: float,
) -> list[dict[str, Any]]:
    if not queries:
        return []
    coros = [_run_single_query(q, max_count, timeout) for q in queries]
    results = await asyncio.gather(*coros, return_exceptions=True)
    merged: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, list):
            merged.extend(r)
    return merged


# ---------------------------------------------------------------------------
# Variant executor
# ---------------------------------------------------------------------------

async def _try_search_variants(
    variants: list[str],
    max_count: int,
) -> list[dict[str, Any]]:
    for i, variant in enumerate(variants):
        try:
            raw = await client_search(
                query=variant,
                max_count=max_count,
                selected_fields=SEARCH_SELECTED_FIELDS,
            )
            items = _format_items(raw)
            if items:
                logger.info(
                    "Variant [%d/%d]: query=%s → %d items",
                    i + 1, len(variants), variant, len(items),
                )
                return items
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Variant [%d/%d] HTTP %d: query=%s",
                i + 1, len(variants), exc.response.status_code, variant,
            )
        except _NETWORK_ERRORS:
            logger.warning(
                "Variant [%d/%d] unreachable: query=%s",
                i + 1, len(variants), variant,
            )
        except Exception as exc:
            logger.warning(
                "Variant [%d/%d] error: query=%s exc=%s",
                i + 1, len(variants), variant, exc,
            )
    return []


# ---------------------------------------------------------------------------
# Mode validators
# ---------------------------------------------------------------------------

def _validate_search_mode(mode: str) -> str | None:
    mode = str(mode).strip().lower()
    if mode not in VALID_SEARCH_MODES:
        return None
    return mode


def _build_search_query(query: str, mode: str) -> str:
    if mode == "name":
        return f"Name:=*{query}*"
    if mode == "description":
        return f"Description:=*{query}*"
    return query


def _build_and_query_for_field(field: str, tokens: list[str]) -> str:
    if field not in {"Name", "Description"}:
        raise ValueError(f"Campo inválido: {field}")
    if not tokens:
        raise ValueError("tokens não pode ser vazio")
    if len(tokens) == 1:
        return f"{field}:=*{tokens[0]}*"
    return " AND ".join(f"{field}:=*{t}*" for t in tokens)


# ---------------------------------------------------------------------------
# Boundary & local filtering (strict AND helpers)
# ---------------------------------------------------------------------------

_BOUNDARY_PATTERN = re.compile(r"[^A-Z0-9]")


def _has_boundary_match(token: str, text: str) -> bool:
    token_up = token.upper()
    text_up = text.upper()
    rgx = re.compile(
        rf"(?:^|{_BOUNDARY_PATTERN.pattern}){re.escape(token_up)}(?:{_BOUNDARY_PATTERN.pattern}|$)"
    )
    return bool(rgx.search(text_up))


def _has_all_tokens_in_text(
    tokens: list[str],
    name: str,
    descriptor: str | None,
) -> bool:
    candidate = f"{name.upper()} {descriptor.upper() if descriptor else ''}"
    for t in tokens:
        t_up = t.upper()
        if _INDUSTRIAL_CODE_REGEX.match(t_up):
            if not _has_boundary_match(t, candidate):
                return False
        elif t_up not in candidate:
            return False
    return True


def _compute_confidence_and_basis(
    item: dict[str, Any],
    tokens: list[str],
) -> tuple[Confidence, list[str]]:
    name = (item.get("name") or "").upper()
    descriptor = (item.get("description") or "").upper()
    candidate = f"{name} {descriptor}"
    basis: list[str] = []

    all_in_name = _has_all_tokens_in_text(tokens, name, None)
    all_in_desc = _has_all_tokens_in_text(tokens, descriptor, None)

    if all_in_name and all_in_desc:
        basis.append("name_contains_all_tokens")
        basis.append("description_contains_all_tokens")
        return (Confidence.HIGH, basis)

    name_normalized = (item.get("name") or "").lower()
    query_normalized = " ".join(tokens)
    if name_normalized == query_normalized:
        basis.append("name_exact")
        return (Confidence.HIGH, basis)

    context_tokens = [t for t in tokens if _INDUSTRIAL_CODE_REGEX.match(t.upper())]
    var_tokens = [t for t in tokens if not _INDUSTRIAL_CODE_REGEX.match(t.upper())]
    context_in_name = bool(context_tokens) and all(
        _has_boundary_match(t, name) for t in context_tokens
    )
    var_in_desc = bool(var_tokens) and all(
        t.upper() in descriptor for t in var_tokens
    )
    var_in_name = bool(var_tokens) and all(
        t.upper() in name for t in var_tokens
    )
    context_in_desc = bool(context_tokens) and all(
        _has_boundary_match(t, descriptor) for t in context_tokens
    )

    if context_in_name and var_in_desc and all(
        _has_boundary_match(t, candidate) if _INDUSTRIAL_CODE_REGEX.match(t.upper())
        else t.upper() in candidate
        for t in tokens
    ):
        basis.append("name_contains_context_token")
        basis.append("description_contains_variable_token")
        return (Confidence.HIGH, basis)

    if all_in_name:
        basis.append("name_contains_all_tokens")
        eng_units = (item.get("engineering_units") or "").upper()
        if eng_units and eng_units != "N/A":
            basis.append("technical_expansion_match")
        return (Confidence.MEDIUM, basis)

    if all_in_desc:
        basis.append("description_contains_all_tokens")
        boundary_count = sum(
            1 for t in tokens if _has_boundary_match(t, candidate)
        )
        if boundary_count >= len(tokens):
            return (Confidence.MEDIUM, basis)
        else:
            basis.append("technical_expansion_match")
            return (Confidence.MEDIUM, basis)

    partial_count = sum(1 for t in tokens if t.upper() in candidate)
    if partial_count >= 2 and partial_count < len(tokens):
        basis.append("technical_expansion_match")
        return (Confidence.LOW, basis)

    return (Confidence.LOW, ["technical_expansion_match"])


# ---------------------------------------------------------------------------
# Response formatters
# ---------------------------------------------------------------------------

def _format_items(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    items_raw = raw_data.get("Items") or []
    items: list[dict[str, Any]] = []
    for item in items_raw:
        name = item.get("Name") or ""
        if not name:
            continue
        items.append(
            {
                "name": name,
                "description": item.get("Descriptor"),
                "web_id": item.get("WebId"),
                "path": f"\\\\{get_domain_settings().PI_SERVER_NAME}\\{name}",
                "point_type": item.get("PointType"),
                "engineering_units": item.get("EngineeringUnits"),
            }
        )
    return items


def _build_output(
    query: str,
    items: list[dict[str, Any]],
    count: int,
    max_count: int,
) -> str:
    if not items:
        return (
            f"Nenhuma tag encontrada para '{query}'. "
            "Para refinar, informe área, equipamento ou parte do nome da tag."
        )
    lines = [f"Encontrei até {max_count} tags candidatas:"]
    for i, item in enumerate(items[:max_count], 1):
        name = item.get("name", "?")
        desc = item.get("description") or ""
        point_type = item.get("point_type") or ""
        eng_units = item.get("engineering_units") or ""
        detalhes = ""
        if point_type:
            detalhes += f" [{point_type}]"
        if eng_units:
            detalhes += f" — {eng_units}"
        if desc:
            lines.append(f"{i}. {name} — {desc}{detalhes}")
        else:
            lines.append(f"{i}. {name}{detalhes}")
    lines.append(
        "Para refinar, informe área, equipamento ou parte do nome da tag."
    )
    return "\n".join(lines)


def _dedup_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = item.get("web_id") or item.get("name")
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Ranking & confidence filtering (strict AND)
# ---------------------------------------------------------------------------


def _rank_and_cap(
    items: list[dict[str, Any]],
    tokens: list[str],
    cap: int = 15,
) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        name = (item.get("name") or "").upper()
        descriptor = (item.get("description") or "").upper()
        candidate = f"{name} {descriptor}"

        all_in_name = _has_all_tokens_in_text(tokens, name, None)
        all_in_desc = _has_all_tokens_in_text(tokens, descriptor, None)

        if name == " ".join(tokens).upper():
            score = 100
        elif all_in_name and all_in_desc:
            score = 80
        elif all_in_name:
            score = 50
        elif all_in_desc:
            score = 30
        else:
            score = 5

        confidence, match_basis = _compute_confidence_and_basis(item, tokens)
        item["confidence"] = confidence.value
        item["matched_concepts"] = list(tokens)
        item["match_basis"] = match_basis

        if confidence == Confidence.LOW:
            continue

        scored.append((score, item))

    scored.sort(key=lambda x: (-x[0], x[1].get("name", "")))
    return [item for _, item in scored[:cap]]


# ---------------------------------------------------------------------------
# Search functions (receive SearchTerms)
# ---------------------------------------------------------------------------

async def _search_description(
    search_terms: SearchTerms,
    max_count: int,
) -> list[dict[str, Any]]:
    if not search_terms.tokens:
        return []
    variants = _build_description_variants(search_terms)
    return await _try_search_variants(variants, max_count)


async def _search_name_with_fallback(
    search_terms: SearchTerms,
    max_count: int,
) -> list[dict[str, Any]]:
    if not search_terms.tokens:
        return []

    name_variants = _build_name_variants(search_terms)
    items = await _try_search_variants(name_variants, max_count)
    if items:
        return items

    nf_variants = _build_namefilter_variants(search_terms)
    for nf in nf_variants:
        try:
            raw = await get_points_by_name_filter(
                name_filter=nf,
                max_count=max_count,
                selected_fields=POINT_SELECTED_FIELDS,
            )
            nf_items = _format_items(raw)
            if nf_items:
                logger.info(
                    "nameFilter fallback: filter=%s → %d items",
                    nf, len(nf_items),
                )
                return nf_items
        except _NETWORK_ERRORS:
            logger.warning(
                "nameFilter fallback unreachable: filter=%s", nf,
            )
        except Exception as exc:
            logger.warning(
                "nameFilter fallback error: filter=%s exc=%s", nf, exc,
            )
    return []


# ---------------------------------------------------------------------------
# Result / error builders
# ---------------------------------------------------------------------------

def _build_result(
    query: str,
    search_mode: str,
    items: list[dict[str, Any]],
    max_count: int,
) -> dict[str, Any]:
    items = items[:max_count]
    count = len(items)
    message = _build_output(query, items, count, max_count)
    return {
        "success": True,
        "query": query,
        "search_mode": search_mode,
        "count": count,
        "max_count": max_count,
        "items": items,
        "message": message,
        "output": message,
    }


def _build_error(
    query: str,
    search_mode: str,
    max_count: int,
    message: str,
) -> dict[str, Any]:
    return {
        "success": False,
        "query": query,
        "search_mode": search_mode,
        "count": 0,
        "max_count": max_count,
        "items": [],
        "message": message,
        "output": message,
    }


def _build_strict_result(
    query: str,
    search_mode: str,
    items: list[dict[str, Any]],
    tokens: list[str],
    max_count: int = 15,
) -> dict[str, Any]:
    ranked = _rank_and_cap(items, tokens, cap=max_count)
    count = len(ranked)
    no_confident_match = count == 0
    refinement_suggested = no_confident_match or (
        count > 0
        and any(item.get("confidence") != "high" for item in ranked)
    )
    if no_confident_match:
        message = (
            "Nenhuma tag correspondente a todos os termos foi encontrada. "
            "Para refinar, informe área, equipamento ou parte do nome da tag."
        )
    else:
        _CONF_LABEL = {"high": "alta confiança", "medium": "confiança média"}
        lines = [f"Encontrei até {count} tag(s):"]
        for i, item in enumerate(ranked[:max_count], 1):
            name = item.get("name", "?")
            desc = item.get("description") or ""
            conf = item.get("confidence", "?")
            conf_label = _CONF_LABEL.get(conf, conf)
            line = f"{i}. {name}"
            if desc:
                line += f" — {desc}"
            line += f" [{conf_label}]"
            lines.append(line)
        lines.append("Para refinar, informe área, equipamento ou parte do nome da tag.")
        message = "\n".join(lines)
    return {
        "success": not no_confident_match,
        "query": query,
        "search_mode": search_mode,
        "count": count,
        "max_count": max_count,
        "items": ranked,
        "no_confident_match": no_confident_match,
        "refinement_suggested": refinement_suggested,
        "message": message,
        "output": message,
    }


async def _build_strict_and_queries(
    search_terms: SearchTerms,
    max_variants: int,
) -> list[str]:
    tokens = search_terms.tokens
    if len(tokens) < 2:
        return [_build_and_query_for_field("Description", tokens)]
    queries: list[str] = []
    queries.append(_build_and_query_for_field("Description", tokens))
    queries.append(_build_and_query_for_field("Name", tokens))
    if max_variants >= 3 and search_terms.variable_terms and (search_terms.equipment_terms or search_terms.area_terms):
        context = search_terms.equipment_terms + search_terms.area_terms
        if context:
            name_part = _build_and_query_for_field("Name", [t.upper() for t in context])
            desc_part = _build_and_query_for_field("Description", search_terms.variable_terms)
            queries.append(f"{name_part} AND {desc_part}")
    if max_variants >= 4 and search_terms.variable_terms and (search_terms.equipment_terms or search_terms.area_terms):
        context = search_terms.equipment_terms + search_terms.area_terms
        if context:
            name_part = _build_and_query_for_field("Name", search_terms.variable_terms)
            desc_part = _build_and_query_for_field("Description", [t.upper() for t in context])
            queries.append(f"{name_part} AND {desc_part}")
    return queries[:max_variants]


async def _search_strict_and(
    search_terms: SearchTerms,
    effective_mode: str,
    internal_max_count: int = 25,
    max_variants: int = 4,
    timeout: float = 30.0,
) -> dict[str, Any]:
    tokens = search_terms.tokens
    if not tokens:
        return _build_error(search_terms.original, effective_mode, 0, "Nenhum termo significativo.")

    queries = await _build_strict_and_queries(search_terms, max_variants)
    if not queries:
        return _build_strict_result(search_terms.original, effective_mode, [], tokens)

    raw_candidates = await _parallel_search(queries, internal_max_count, timeout)
    deduped = _dedup_items(raw_candidates)
    return _build_strict_result(search_terms.original, effective_mode, deduped, tokens)


def _detect_advanced_query(query: str) -> bool:
    return bool(re.search(r"(Description|Name)\s*:=", query))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def search_pi_points(
    query: str,
    max_count: int = _DEFAULT_MAX_COUNT,
    search_mode: str = "auto",
) -> dict[str, Any]:
    query_sanitized = _sanitize_query(query)
    if query_sanitized is None:
        return _build_error(
            query, search_mode, 0,
            "A query de busca não pode estar vazia.",
        )

    effective_max_count = _validate_max_count(max_count)
    effective_mode = _validate_search_mode(search_mode)
    if effective_mode is None:
        return _build_error(
            query_sanitized, search_mode, effective_max_count,
            f"Modo de busca inválido: '{search_mode}'. "
            "Use auto, name, description ou query.",
        )

    # ── Extract structured search terms ──
    search_terms = _extract_search_terms(query_sanitized)

    # ── query mode with unrecognized syntax → fallback to auto ──
    if effective_mode == "query" and not _detect_advanced_query(query_sanitized):
        effective_mode = "auto"

    # ── Strict AND path (feature flag) ──
    try:
        from mcp_server.core.config import settings as _mcp_settings

        if _mcp_settings.ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND and effective_mode in ("auto", "name", "description"):
            _tokens = search_terms.tokens
            if len(_tokens) >= 2:
                return await _search_strict_and(
                    search_terms,
                    effective_mode,
                    internal_max_count=_mcp_settings.MCP_SEARCH_PI_POINTS_INTERNAL_MAX_COUNT,
                    max_variants=_mcp_settings.MCP_SEARCH_PI_POINTS_MAX_VARIANTS,
                    timeout=_mcp_settings.MCP_SEARCH_PI_POINTS_TIMEOUT_SECONDS,
                )
    except ImportError:
        pass

    # ── auto mode ──
    if effective_mode == "auto":
        items_desc: list[dict[str, Any]] = []
        try:
            items_desc = await _search_description(
                search_terms, effective_max_count,
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Auto description HTTP error [%d]: query=%s",
                exc.response.status_code, query_sanitized,
            )
        except _NETWORK_ERRORS as exc:
            logger.warning("Auto description unreachable: %s", exc)
        except Exception as exc:
            logger.warning("Auto description unexpected error: %s", exc)

        if len(items_desc) >= effective_max_count:
            return _build_result(
                query_sanitized, "auto", items_desc[:effective_max_count],
                effective_max_count,
            )

        items_name = await _search_name_with_fallback(
            search_terms, effective_max_count,
        )

        merged = _dedup_items(items_desc + items_name)
        return _build_result(
            query_sanitized, "auto", merged, effective_max_count,
        )

    # ── non-auto modes ──
    if effective_mode == "description":
        items = await _search_description(
            search_terms, effective_max_count,
        )
        return _build_result(
            query_sanitized, effective_mode, items, effective_max_count,
        )

    if effective_mode == "name":
        items = await _search_name_with_fallback(
            search_terms, effective_max_count,
        )
        return _build_result(
            query_sanitized, effective_mode, items, effective_max_count,
        )

    # query mode: pass raw query directly
    try:
        raw_data = await client_search(
            query=query_sanitized,
            max_count=effective_max_count,
            selected_fields=SEARCH_SELECTED_FIELDS,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Query search error [%d]: query=%s",
            exc.response.status_code, query_sanitized,
        )
        return _build_error(
            query_sanitized, effective_mode, effective_max_count,
            f"Erro ao consultar a PI Web API (HTTP {exc.response.status_code}).",
        )
    except _NETWORK_ERRORS as exc:
        logger.warning("PI Web API unreachable: %s", exc)
        return _build_error(
            query_sanitized, effective_mode, effective_max_count,
            "A PI Web API está temporariamente indisponível. Tente novamente.",
        )
    except Exception as exc:
        logger.warning("Unexpected error in search_pi_points: %s", exc)
        return _build_error(
            query_sanitized, effective_mode, effective_max_count,
            f"Erro inesperado ao buscar tags: {exc}",
        )

    items = _format_items(raw_data)
    return _build_result(
        query_sanitized, effective_mode, items, effective_max_count,
    )
