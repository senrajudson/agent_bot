"""Regressão: nenhum módulo de produção do MCP pode hackear sys.path."""
from __future__ import annotations

import re
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[2] / "mcp_server"
PATTERN = re.compile(r"sys\.path\.(insert|append|extend)")


def test_no_syspath_hacks_in_production():
    offenders: list[str] = []
    for py in MCP_ROOT.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        if ".venv" in py.parts:
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if PATTERN.search(line):
                rel = py.relative_to(MCP_ROOT.parent)
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, "sys.path hacks em produção:\n" + "\n".join(offenders)
