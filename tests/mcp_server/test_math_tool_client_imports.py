"""Regression test for ModuleNotFoundError on tenacity in mcp_server.

Validates that the modules imported by mcp_server's tools can be loaded
in a Python interpreter that has tenacity installed. This is the same
failure mode that previously broke tag_statistics and tag_calculus in PRD.
"""
from __future__ import annotations

import importlib
import sys

import pytest


def test_tenacity_is_installed() -> None:
    """Confirm tenacity is resolvable in this environment."""
    import tenacity  # noqa: F401
    assert hasattr(tenacity, "retry")


@pytest.mark.parametrize(
    "module_name",
    [
        "domain.analytics.clients.math_tool_client",
        "domain.analytics.services.math_tool_service",
    ],
)
def test_module_imports_without_module_not_found_error(module_name: str) -> None:
    """Import the critical chain and ensure no ModuleNotFoundError."""
    if module_name not in sys.modules:
        importlib.import_module(module_name)


def test_post_math_tool_decorator_is_retry() -> None:
    """Verify the @retry decorator from tenacity was applied at import time."""
    from domain.analytics.clients.math_tool_client import _post_math_tool
    assert hasattr(_post_math_tool, "retry")
    assert hasattr(_post_math_tool, "retry_with")
