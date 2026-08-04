"""Regressão: nenhum módulo de mcp_server/ pode importar top-level bare."""
from __future__ import annotations

import ast
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[2] / "mcp_server"
BANNED = {"core", "services", "clients", "schemas", "utils"}


def _is_bare_import(node: ast.AST) -> bool:
    if isinstance(node, ast.ImportFrom) and node.module:
        return node.module.split(".")[0] in BANNED
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] in BANNED for alias in node.names)
    return False


def test_no_bare_top_level_imports():
    offenders: list[str] = []
    for py in MCP_ROOT.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        if ".venv" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if _is_bare_import(node):
                rel = py.relative_to(MCP_ROOT.parent)
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, "Imports bare encontrados:\n" + "\n".join(offenders)
