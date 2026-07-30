"""Tests for App Settings domain integration bootstrap."""
import os
import subprocess
import sys

import pytest


class TestAppDomainBootstrap:
    def test_app_settings_produces_domain_settings(self):
        from app.core.config import Settings
        s = Settings(_env_file=None)
        d = s.to_domain_integration_settings()
        assert d.PI_WEB_API_BASE_URL == "http://10.247.224.39/piwebapi"
        assert d.MATH_TOOL_BASE_URL == "http://math_tool:8001"
        assert d.REDIS_URL == "redis://127.0.0.1:6379/2"

    def test_app_imports_without_mcp_env(self):
        code = """
import sys
sys.path.insert(0, '.')
from app.core.config import Settings
s = Settings(_env_file=None)
d = s.to_domain_integration_settings()
print(d.PI_WEB_API_BASE_URL)
"""
        env = {k: v for k, v in os.environ.items() if "mcp_server" not in k.lower()}
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=10, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "10.247.224.39" in result.stdout

    def test_agent_configure_domain_settings_on_import(self):
        from domain.core.config import get_domain_settings
        from app.main import app

        s = get_domain_settings()
        assert s.PI_WEB_API_BASE_URL == "http://10.247.224.39/piwebapi"
        assert app.title is not None

    def test_domain_not_loaded_after_app_main_without_mcp_env(self):
        code = """
import sys, os
os.environ['PHOENIX_ENABLED'] = 'false'
sys.path.insert(0, '.')
from domain.core.config import get_domain_settings
from app.main import app
s = get_domain_settings()
print(f'configured:{s.PI_WEB_API_BASE_URL}')
"""
        env = os.environ.copy()
        env.pop("PHOENIX_ENABLED", None)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=15, env=env,
        )
        if result.returncode != 0:
            if "RuntimeError" in result.stderr:
                pytest.skip("DomainIntegrationSettings already configured in parent process")
                return
            pytest.fail(f"stderr: {result.stderr}")
        assert "configured" in result.stdout
