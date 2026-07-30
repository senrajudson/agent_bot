import os
import pytest


@pytest.fixture(autouse=True)
def _auto_configure_domain_settings():
    from domain.core.config import (
        _reset_domain_settings,
        configure_domain_settings,
    )
    from domain.core.integration_settings import DomainIntegrationSettings

    try:
        _reset_domain_settings(test_only=True)
    except RuntimeError:
        pass

    configure_domain_settings(DomainIntegrationSettings(
        PI_WEB_API_BASE_URL="http://pi.test/piwebapi",
        PI_SERVER_NAME="PIMS",
        MATH_TOOL_BASE_URL="http://math.test",
        REDIS_URL="redis://localhost:6379/2",
    ))
    yield
