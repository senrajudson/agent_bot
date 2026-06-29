"""CQRS audit tests — Prompt 4 Cycle 1.

Freezes the current catalog of 6 Commands + 5 Queries, validates that
Queries contain no write/publish side effects, and documents known
anomalies as accepted state.

No production code is modified. The test is fully isolated (no network,
no Redis, no Qdrant, no LLM).
"""
from __future__ import annotations

import importlib
import inspect
import pathlib
import re

import pytest

from app.application.commands.base import Command
from app.application.queries.base import Query


# ---------------------------------------------------------------------------
# Frozen catalog constants
# ---------------------------------------------------------------------------

EXPECTED_COMMANDS: tuple[str, ...] = (
    "ExtractOcr",
    "RouteMessage",
    "RunAgentForMessage",
    "SaveConversationTurn",
    "RetrieveKnowledgeContext",
    "InvokeMcpTool",
)

EXPECTED_QUERIES: tuple[str, ...] = (
    "GetConversationMemory",
    "GetKnowledgeContext",
    "GetPiTagCurrentValue",
    "GetPiHistoricalSeries",
    "GetPimsStatus",
)

# Patterns that must NOT appear in Query source (outside comments/docstrings).
FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"\bEventPublisher\b",
    r"\bEventStore\b",
    r"\.publish\(",
    r"\.append\(",
    r"\.append_batch\(",
    r"\brpush\b",
    r"\bsetnx\b",
    r"\bxadd\b",
    r"\bdelete\b",
)

# Known anomalies accepted as current state — documented, not corrected.
KNOWN_ANOMALIES: tuple[str, ...] = (
    "RetrieveKnowledgeContext in commands/",
    "GetKnowledgeContext orfa",
    "dupla-publicacao-eventos-memoria",
)

# Mapping from Query class name to module name (explicit to avoid inflection).
_QUERY_MODULE_MAP: dict[str, str] = {
    "GetConversationMemory": "get_conversation_memory",
    "GetKnowledgeContext": "get_knowledge_context",
    "GetPiTagCurrentValue": "get_pi_tag_current_value",
    "GetPiHistoricalSeries": "get_pi_historical_series",
    "GetPimsStatus": "get_pims_status",
}

COMMANDS_DIR = pathlib.Path("app/application/commands")
QUERIES_DIR = pathlib.Path("app/application/queries")


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _discover_classes(base_cls: type, pkg_dir: pathlib.Path) -> set[str]:
    """Import each module in *pkg_dir* and collect subclass names of *base_cls*."""
    found: set[str] = set()
    for py_file in sorted(pkg_dir.glob("*.py")):
        if py_file.name in {"base.py", "__init__.py"}:
            continue
        module_name = f"app.application.{pkg_dir.name}.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            pytest.fail(f"Failed to import {module_name}: {exc}")
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj is base_cls:
                continue
            if not issubclass(obj, base_cls):
                continue
            if getattr(obj, "__module__", None) != module_name:
                continue
            found.add(obj.__name__)
    return found


def _strip_comments_and_docstrings(source: str) -> str:
    """Remove comments (#) and triple-quote docstrings from *source*.

    Simple state-machine: toggles ``in_triple`` when a triple delimiter is
    found. Lines inside a docstring are dropped entirely. Inline ``#``
    comments are stripped from the remainder.
    """
    result: list[str] = []
    in_triple: str | None = None

    for line in source.splitlines():
        if in_triple:
            if in_triple in line:
                # Close the docstring on this line
                idx = line.index(in_triple)
                line = line[idx + len(in_triple) :]
                in_triple = None
            else:
                continue  # entire line inside docstring

        # Detect triple-quote opening
        for delim in ('"""', "'''"):
            if delim in line:
                if line.count(delim) == 2:
                    # Single-line docstring: remove both delimiters
                    line = line.replace(delim, "")
                else:
                    in_triple = delim
                    line = line.split(delim, 1)[0]
                    break

        # Strip inline comment (heuristic: first # not inside a string)
        if "#" in line:
            line = line[: line.index("#")]

        if line.strip():
            result.append(line)

    return "\n".join(result)


def _scan_query_source(
    query_name: str, source: str, source_file: pathlib.Path
) -> list[tuple[str, int, str]]:
    """Return list of ``(pattern, line_no, line_content)`` hits in *source*."""
    cleaned = _strip_comments_and_docstrings(source)
    hits: list[tuple[str, int, str]] = []
    lines = cleaned.splitlines()
    for line_no, line in enumerate(lines, start=1):
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                hits.append((pattern, line_no, line.strip()))
    return hits


# ---------------------------------------------------------------------------
# Tests: Command catalog
# ---------------------------------------------------------------------------


class TestCommandsCatalog:
    def test_all_commands_discovered(self) -> None:
        discovered = _discover_classes(Command, COMMANDS_DIR)
        expected = set(EXPECTED_COMMANDS)
        missing = sorted(expected - discovered)
        extra = sorted(discovered - expected)
        assert discovered == expected, (
            f"Command catalog divergent.\n"
            f"  Expected:  {sorted(expected)}\n"
            f"  Found:     {sorted(discovered)}\n"
            f"  Missing:   {missing}\n"
            f"  Extra:     {extra}"
        )

    def test_no_duplicate_command_names(self) -> None:
        discovered = _discover_classes(Command, COMMANDS_DIR)
        assert len(discovered) == len(EXPECTED_COMMANDS), (
            f"Quantity divergent. "
            f"Expected {len(EXPECTED_COMMANDS)}, found {len(discovered)}."
        )


# ---------------------------------------------------------------------------
# Tests: Query catalog
# ---------------------------------------------------------------------------


class TestQueriesCatalog:
    def test_all_queries_discovered(self) -> None:
        discovered = _discover_classes(Query, QUERIES_DIR)
        expected = set(EXPECTED_QUERIES)
        missing = sorted(expected - discovered)
        extra = sorted(discovered - expected)
        assert discovered == expected, (
            f"Query catalog divergent.\n"
            f"  Expected:  {sorted(expected)}\n"
            f"  Found:     {sorted(discovered)}\n"
            f"  Missing:   {missing}\n"
            f"  Extra:     {extra}"
        )


# ---------------------------------------------------------------------------
# Tests: Query purity
# ---------------------------------------------------------------------------


class TestQueriesPurity:
    @pytest.mark.parametrize("query_name", EXPECTED_QUERIES)
    def test_query_has_no_writes_or_publishes(self, query_name: str) -> None:
        module_stem = _QUERY_MODULE_MAP.get(query_name)
        if module_stem is None:
            pytest.fail(
                f"Query {query_name} has no module mapping in _QUERY_MODULE_MAP."
            )

        module_name = f"app.application.queries.{module_stem}"
        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, query_name)
            source_file = pathlib.Path(inspect.getfile(cls))
        except Exception as exc:
            pytest.fail(f"Failed to locate {query_name}: {exc}")

        source = source_file.read_text(encoding="utf-8")
        hits = _scan_query_source(query_name, source, source_file)
        assert not hits, (
            f"Query {query_name} contains forbidden patterns "
            f"in {source_file}:\n"
            + "\n".join(
                f"  pattern={p!r}  line={ln}  content={c!r}"
                for p, ln, c in hits
            )
        )


# ---------------------------------------------------------------------------
# Tests: Known anomalies
# ---------------------------------------------------------------------------


class TestKnownAnomalies:
    def test_known_anomalies_declared(self) -> None:
        assert len(KNOWN_ANOMALIES) >= 1, (
            "KNOWN_ANOMALIES must be a non-empty tuple."
        )
        expected_anomalies = {
            "RetrieveKnowledgeContext in commands/",
            "GetKnowledgeContext orfa",
            "dupla-publicacao-eventos-memoria",
        }
        missing = expected_anomalies - set(KNOWN_ANOMALIES)
        assert not missing, (
            f"Expected anomalies missing from KNOWN_ANOMALIES: {sorted(missing)}"
        )

    def test_known_anomalies_are_unique(self) -> None:
        assert len(KNOWN_ANOMALIES) == len(set(KNOWN_ANOMALIES)), (
            "KNOWN_ANOMALIES contains duplicates."
        )
