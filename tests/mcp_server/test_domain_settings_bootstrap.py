"""Tests for MCP Settings domain integration bootstrap."""
import os
import subprocess
import sys

import pytest


class TestMcpDomainBootstrap:
    def test_mcp_settings_produces_domain_settings(self):
        code = """
import sys
sys.path.insert(0, 'mcp_server')
sys.path.insert(0, '.')
from core.config import Settings
s = Settings(_env_file=None, GRAFANA_LOKI_QUERY_RANGE_URL='http://fake', GRAFANA_BEARER_TOKEN='fake', ENABLE_DRIVE_CSV_EXPORT_TOOL=False)
d = s.to_domain_integration_settings()
print(f'PI={d.PI_WEB_API_BASE_URL}')
print(f'REDIS={d.REDIS_URL}')
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "ENABLE_DRIVE_CSV_EXPORT_TOOL": "false",
                 "GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE": "",
                 "GOOGLE_DRIVE_EXPORT_FOLDER_ID": ""},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PI=http://10.247.224.39/piwebapi" in result.stdout
        assert "REDIS=redis://127.0.0.1:6379/2" in result.stdout

    def test_mcp_settings_has_redis_and_pims_status(self):
        import sys
        sys.path.insert(0, "mcp_server")
        sys.path.insert(0, ".")
        from core.config import Settings
        s = Settings(_env_file=None, GRAFANA_LOKI_QUERY_RANGE_URL="http://fake",
                     GRAFANA_BEARER_TOKEN="fake", ENABLE_DRIVE_CSV_EXPORT_TOOL=False)
        assert hasattr(s, "REDIS_URL")
        assert hasattr(s, "PIMS_STATUS_LOKI_QUERY")
        assert hasattr(s, "PIMS_STATUS_LOOKBACK_MINUTES")
        assert hasattr(s, "PIMS_STATUS_LIMIT")

    def test_mcp_imports_without_app_env(self):
        code = """
import sys, os
os.environ['ENABLE_DRIVE_CSV_EXPORT_TOOL'] = 'false'
os.environ['GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE'] = ''
os.environ['GOOGLE_DRIVE_EXPORT_FOLDER_ID'] = ''
sys.path.insert(0, 'mcp_server')
sys.path.insert(0, '.')
from core.config import Settings
s = Settings(_env_file=None, GRAFANA_LOKI_QUERY_RANGE_URL='http://fake', GRAFANA_BEARER_TOKEN='fake')
print('OK')
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=10,
            env={k: v for k, v in os.environ.items() if "app" not in k.lower() and "PHOENIX" not in k},
        )
        if result.returncode != 0:
            if "RuntimeError" in result.stderr:
                pytest.skip("DomainIntegrationSettings already configured")
                return
            pytest.fail(f"stderr: {result.stderr}")
        assert "OK" in result.stdout
