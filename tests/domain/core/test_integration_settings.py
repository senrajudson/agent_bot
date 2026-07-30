"""Tests for DomainIntegrationSettings contract."""
import os
import subprocess
import sys

import pytest

from domain.core.integration_settings import DomainIntegrationSettings


class TestDomainIntegrationSettings:
    def test_all_fields_present(self):
        fields = set(DomainIntegrationSettings.model_fields.keys())
        expected = {
            "PI_WEB_API_BASE_URL", "PI_SERVER_NAME", "PI_WEB_API_USERNAME",
            "PI_WEB_API_PASSWORD", "PI_WEB_API_VERIFY_SSL",
            "MATH_TOOL_BASE_URL", "MATH_TOOL_TIMEOUT_SECONDS",
            "REDIS_URL",
        }
        assert fields == expected, f"Fields mismatch: {fields ^ expected}"

    def test_defaults_match_domain_config(self):
        s = DomainIntegrationSettings()
        assert s.PI_WEB_API_BASE_URL == "http://10.247.224.39/piwebapi"
        assert s.PI_SERVER_NAME == "PIMS"
        assert s.PI_WEB_API_USERNAME is None
        assert s.PI_WEB_API_PASSWORD is None
        assert s.PI_WEB_API_VERIFY_SSL is False
        assert s.MATH_TOOL_BASE_URL == "http://math_tool:8001"
        assert s.MATH_TOOL_TIMEOUT_SECONDS == 120.0
        assert s.REDIS_URL == "redis://127.0.0.1:6379/2"

    def test_frozen(self):
        s = DomainIntegrationSettings()
        with pytest.raises(Exception):
            s.PI_WEB_API_BASE_URL = "http://other"

    def test_secrets_protected_in_repr(self):
        s = DomainIntegrationSettings(
            PI_WEB_API_PASSWORD="secret123",
        )
        r = repr(s)
        assert "secret123" not in r

    def test_secrets_accessible_via_attribute(self):
        s = DomainIntegrationSettings(
            PI_WEB_API_PASSWORD="secret123",
        )
        assert s.PI_WEB_API_PASSWORD == "secret123"

    def test_not_BaseSettings(self):
        from pydantic import BaseModel
        assert issubclass(DomainIntegrationSettings, BaseModel)
        assert "BaseSettings" not in [c.__name__ for c in DomainIntegrationSettings.__mro__]

    def test_custom_values(self):
        s = DomainIntegrationSettings(
            PI_WEB_API_BASE_URL="http://custom",
            MATH_TOOL_BASE_URL="http://math:8001",
            REDIS_URL="redis://other:6379/0",
        )
        assert s.PI_WEB_API_BASE_URL == "http://custom"
        assert s.MATH_TOOL_BASE_URL == "http://math:8001"
        assert s.REDIS_URL == "redis://other:6379/0"

    def test_extra_forbidden(self):
        with pytest.raises(Exception):
            DomainIntegrationSettings(INVALID_FIELD="x")

    def test_no_env_loading_on_import(self):
        code = """
import sys
sys.path.insert(0, '.')
from domain.core.integration_settings import DomainIntegrationSettings
s = DomainIntegrationSettings()
print(s.PI_WEB_API_BASE_URL)
"""
        env = {k: v for k, v in os.environ.items() if "PI_" not in k}
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=10, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "http" in result.stdout
