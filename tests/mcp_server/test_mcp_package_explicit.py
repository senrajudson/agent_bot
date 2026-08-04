"""mcp_server é um pacote explícito e importável sem side effects."""
from __future__ import annotations

import logging
import warnings
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_server_init_exists():
    assert (MCP_ROOT / "mcp_server" / "__init__.py").is_file()


def test_mcp_server_init_is_empty():
    content = (MCP_ROOT / "mcp_server" / "__init__.py").read_text(encoding="utf-8").strip()
    assert content == "", f"mcp_server/__init__.py deve estar vazio: {content!r}"


def test_mcp_server_import_has_no_errors(caplog):
    caplog.set_level(logging.ERROR)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        import mcp_server  # noqa: F401
    assert not caplog.records
