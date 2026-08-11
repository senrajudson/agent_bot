"""Tests that validate mcp_server/pyproject.toml declares all runtime
dependencies correctly.

These tests catch the class of bug where code in mcp_server/ imports a
third-party package but the dependency is declared only in the root
pyproject.toml, not in mcp_server/pyproject.toml — causing ModuleNotFoundError
inside the pi_mcp_server Docker image.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

MCP_PYPROJECT = Path(__file__).resolve().parents[2] / "mcp_server" / "pyproject.toml"


@pytest.fixture(scope="module")
def mcp_manifest() -> dict:
    """Parse mcp_server/pyproject.toml once per test module."""
    return tomllib.loads(MCP_PYPROJECT.read_text(encoding="utf-8"))


class TestOpenpyxlDeclared:
    """openpyxl must be declared in mcp_server/pyproject.toml (not only root)."""

    def test_openpyxl_in_manifest(self, mcp_manifest: dict) -> None:
        deps = mcp_manifest.get("project", {}).get("dependencies", [])
        openpyxl_entries = [d for d in deps if d.strip().startswith("openpyxl")]
        assert openpyxl_entries, (
            "openpyxl must be declared in mcp_server/pyproject.toml [project].dependencies"
        )

    def test_openpyxl_range(self, mcp_manifest: dict) -> None:
        deps = mcp_manifest.get("project", {}).get("dependencies", [])
        openpyxl_entries = [d for d in deps if d.strip().startswith("openpyxl")]
        assert openpyxl_entries, "openpyxl not found"
        entry = openpyxl_entries[0]
        assert ">=3.1.0" in entry, f"Expected >=3.1.0 in range, got: {entry}"
        assert "<4.0.0" in entry, f"Expected <4.0.0 in range, got: {entry}"

    def test_manifest_is_mcp_not_root(self) -> None:
        """Ensure we are reading mcp_server/pyproject.toml, not the root one."""
        assert "mcp_server" in str(MCP_PYPROJECT), (
            f"Expected path to contain 'mcp_server', got: {MCP_PYPROJECT}"
        )


class TestManifestStructure:
    """Basic structural checks on the MCP manifest."""

    def test_package_mode_false(self, mcp_manifest: dict) -> None:
        poetry = mcp_manifest.get("tool", {}).get("poetry", {})
        assert poetry.get("package-mode") is False, (
            "mcp_server pyproject.toml must have package-mode = false"
        )

    def test_has_project_dependencies(self, mcp_manifest: dict) -> None:
        deps = mcp_manifest.get("project", {}).get("dependencies", [])
        assert len(deps) >= 1, "mcp_server/pyproject.toml must have at least 1 dependency"

    def test_no_duplicate_openpyxl(self, mcp_manifest: dict) -> None:
        deps = mcp_manifest.get("project", {}).get("dependencies", [])
        openpyxl_entries = [d for d in deps if d.strip().startswith("openpyxl")]
        assert len(openpyxl_entries) == 1, (
            f"Expected exactly 1 openpyxl entry, found {len(openpyxl_entries)}"
        )
