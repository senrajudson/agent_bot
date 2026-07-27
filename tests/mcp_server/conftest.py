import pytest


@pytest.fixture(autouse=True)
def _reset_domain_for_mcp_tests():
    """Reset DomainIntegrationSettings before each MCP test.

    This ensures tests that import mcp_server/server.py (which configures
    the provider at module level) don't conflict with provider state
    left by previous tests.
    """
    from domain.core.config import _reset_domain_settings, get_domain_settings

    try:
        _reset_domain_settings(test_only=True)
    except RuntimeError:
        pass
    yield
