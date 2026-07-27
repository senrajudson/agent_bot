"""Tests for domain config provider (configure/get/reset)."""
import threading

import pytest

from domain.core.config import (
    configure_domain_settings,
    get_domain_settings,
    _reset_domain_settings,
)
from domain.core.integration_settings import DomainIntegrationSettings


@pytest.fixture(autouse=True)
def reset_provider():
    _reset_domain_settings(test_only=True)
    yield


class TestProvider:
    def test_get_before_configure_raises(self):
        with pytest.raises(RuntimeError, match="não foi configurado"):
            get_domain_settings()

    def test_configure_accepts_first(self):
        s = DomainIntegrationSettings()
        configure_domain_settings(s)
        assert get_domain_settings() is s

    def test_reconfigure_divergent_raises(self):
        s1 = DomainIntegrationSettings(PI_WEB_API_BASE_URL="http://a")
        s2 = DomainIntegrationSettings(PI_WEB_API_BASE_URL="http://b")
        configure_domain_settings(s1)
        with pytest.raises(RuntimeError, match="já foi configurado"):
            configure_domain_settings(s2)

    def test_get_returns_same_object(self):
        s = DomainIntegrationSettings()
        configure_domain_settings(s)
        assert get_domain_settings() is s
        assert get_domain_settings().PI_WEB_API_BASE_URL == s.PI_WEB_API_BASE_URL

    def test_reset_without_test_only_raises(self):
        with pytest.raises(RuntimeError, match="apenas em testes"):
            _reset_domain_settings()

    def test_reset_with_test_only_works(self):
        s = DomainIntegrationSettings()
        configure_domain_settings(s)
        assert get_domain_settings() is s
        _reset_domain_settings(test_only=True)
        with pytest.raises(RuntimeError, match="não foi configurado"):
            get_domain_settings()

    def test_concurrent_configure_only_one_wins(self):
        results = []
        errors = []

        def try_configure(val: str):
            try:
                s = DomainIntegrationSettings(PI_WEB_API_BASE_URL=f"http://{val}")
                configure_domain_settings(s)
                results.append(val)
            except RuntimeError as e:
                errors.append(str(e))

        t1 = threading.Thread(target=try_configure, args=("a",))
        t2 = threading.Thread(target=try_configure, args=("b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 1, f"Expected 1 success, got {results}"
        assert len(errors) == 1, f"Expected 1 error, got {errors}"

    def test_no_env_file_loaded_on_import(self):
        import subprocess
        import sys
        code = """
import sys
sys.path.insert(0, '.')
from domain.core.config import configure_domain_settings, get_domain_settings
from domain.core.integration_settings import DomainIntegrationSettings

# Should NOT fail at import time
print("import_ok")

# Should fail on access (not configured)
try:
    get_domain_settings()
    print("ERROR: should raise")
except RuntimeError:
    print("fail_before_configure_ok")

# Configure should work
s = DomainIntegrationSettings(PI_WEB_API_BASE_URL="http://test")
configure_domain_settings(s)
print(f"get_ok:{get_domain_settings().PI_WEB_API_BASE_URL}")
"""
        env = {k: v for k, v in __import__('os').environ.items()}
        result = __import__('subprocess').run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=10, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "import_ok" in result.stdout
        assert "fail_before_configure_ok" in result.stdout
        assert "get_ok:http://test" in result.stdout
