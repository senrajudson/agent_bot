"""
tests/unit/test_qa_environment_validator.py

Suíte de testes unitários 100% offline para o validador operacional qa/validate_environment.py.
Valida o comportamento fail-closed, parsing, sanitização, mocks de Redis/HTTP e exit codes.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from qa.validate_environment import (
    ALLOWED_ARTIFACT_ROOT,
    EXPECTED_API_ARTIFACTS_DIR,
    EXPECTED_MCP_ARTIFACTS_DIR,
    EXPECTED_MCP_SERIES_CSV_DIR,
    EXPECTED_PHOENIX_PROJECT,
    AggregatedStatus,
    CheckStatus,
    is_path_safe_under_root,
    load_effective_config,
    main,
    parse_otel_attributes,
    run_api_health_check,
    run_redis_ping_check,
    run_static_preflight,
    sanitize_text,
    validate_environment,
)


@pytest.fixture
def valid_qa_config() -> dict[str, str]:
    return {
        "APP_ENV": "qa",
        "REDIS_URL": "redis://127.0.0.1:6380/0",
        "REDIS_KEY_PREFIX": "pi_chat:qa:memory",
        "AGENT_ARTIFACTS_BASE_DIR": EXPECTED_API_ARTIFACTS_DIR,
        "MCP_ARTIFACT_TEMP_DIR": EXPECTED_MCP_ARTIFACTS_DIR,
        "MCP_SERIES_CSV_PUBLISH_TEMP_DIR": EXPECTED_MCP_SERIES_CSV_DIR,
        "PHOENIX_PROJECT_NAME": EXPECTED_PHOENIX_PROJECT,
        "OTEL_RESOURCE_ATTRIBUTES": "deployment.environment=qa,app.channel=n8n",
    }


def test_parse_otel_attributes():
    attrs = parse_otel_attributes("deployment.environment=qa, app.channel=n8n, invalid, key=val=extra")
    assert attrs.get("deployment.environment") == "qa"
    assert attrs.get("app.channel") == "n8n"
    assert attrs.get("key") == "val=extra"
    assert "invalid" not in attrs


def test_is_path_safe_under_root(tmp_path):
    # Raiz válida
    root = str(tmp_path / "agent_bot_qa")
    sub = f"{root}/api_artifacts"

    # Criar estruturas no tmp_path para verificação real
    (tmp_path / "agent_bot_qa" / "api_artifacts").mkdir(parents=True, exist_ok=True)

    assert is_path_safe_under_root(sub, root) is True
    # Não pode ser igual à raiz
    assert is_path_safe_under_root(root, root) is False
    # Não pode ser relativo
    assert is_path_safe_under_root("relative/path", root) is False
    # Path traversal não pode escapar da raiz
    assert is_path_safe_under_root(f"{sub}/../../outside", root) is False


def test_sanitize_text():
    url_with_pass = "redis://:secret123@127.0.0.1:6380/0"
    sanitized = sanitize_text(url_with_pass)
    assert "secret123" not in sanitized
    assert "***" in sanitized


def test_load_effective_config_precedence(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.qa"
    env_file.write_text("APP_ENV=qa\nREDIS_URL=redis://127.0.0.1:6380/0\n")

    # Override do processo deve prevalecer
    monkeypatch.setenv("APP_ENV", "qa_override")

    cfg = load_effective_config(str(env_file))
    assert cfg["APP_ENV"] == "qa_override"
    assert cfg["REDIS_URL"] == "redis://127.0.0.1:6380/0"


def test_static_preflight_valid(valid_qa_config):
    checks = run_static_preflight(valid_qa_config, "http://127.0.0.1:8002")
    assert len(checks) == 10
    assert all(c.status == CheckStatus.PASS for c in checks)


def test_static_preflight_invalid_app_env(valid_qa_config):
    valid_qa_config["APP_ENV"] = "production"
    checks = run_static_preflight(valid_qa_config, "http://127.0.0.1:8002")
    env_check = next(c for c in checks if c.name == "environment")
    assert env_check.status == CheckStatus.BLOCKED
    assert "production" in env_check.detail


def test_static_preflight_remote_redis(valid_qa_config):
    # Host remoto
    valid_qa_config["REDIS_URL"] = "redis://10.0.0.1:6380/0"
    checks = run_static_preflight(valid_qa_config, "http://127.0.0.1:8002")
    redis_check = next(c for c in checks if c.name == "redis_configuration")
    assert redis_check.status == CheckStatus.BLOCKED
    assert "10.0.0.1" in redis_check.detail

    # Porta de produção (6379)
    valid_qa_config["REDIS_URL"] = "redis://127.0.0.1:6379/0"
    checks = run_static_preflight(valid_qa_config, "http://127.0.0.1:8002")
    redis_check = next(c for c in checks if c.name == "redis_configuration")
    assert redis_check.status == CheckStatus.BLOCKED
    assert "6379" in redis_check.detail


def test_static_preflight_invalid_prefix(valid_qa_config):
    valid_qa_config["REDIS_KEY_PREFIX"] = "pi_chat:memory"  # Prefixo legado
    checks = run_static_preflight(valid_qa_config, "http://127.0.0.1:8002")
    mem_check = next(c for c in checks if c.name == "memory_namespace")
    assert mem_check.status == CheckStatus.BLOCKED


def test_static_preflight_remote_api(valid_qa_config):
    # Host remoto
    checks = run_static_preflight(valid_qa_config, "http://192.168.1.100:8002")
    api_check = next(c for c in checks if c.name == "api_url_security")
    assert api_check.status == CheckStatus.BLOCKED

    # HTTPS remoto
    checks = run_static_preflight(valid_qa_config, "https://remote-server.com:8002")
    api_check = next(c for c in checks if c.name == "api_url_security")
    assert api_check.status == CheckStatus.BLOCKED


def test_static_preflight_invalid_artifact_path(valid_qa_config):
    valid_qa_config["AGENT_ARTIFACTS_BASE_DIR"] = "/tmp/agent_bot_artifacts"  # Path default de produção
    checks = run_static_preflight(valid_qa_config, "http://127.0.0.1:8002")
    art_check = next(c for c in checks if c.name == "artifact_api_path")
    assert art_check.status == CheckStatus.BLOCKED


def test_static_preflight_invalid_phoenix_project(valid_qa_config):
    valid_qa_config["PHOENIX_PROJECT_NAME"] = "pi-chat-api"  # Projeto de produção
    checks = run_static_preflight(valid_qa_config, "http://127.0.0.1:8002")
    phx_check = next(c for c in checks if c.name == "phoenix_project")
    assert phx_check.status == CheckStatus.BLOCKED


@patch("redis.Redis")
def test_redis_ping_success(mock_redis_cls):
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_redis_cls.return_value = mock_client

    res = run_redis_ping_check("redis://127.0.0.1:6380/0", timeout=2.0)
    assert res.status == CheckStatus.PASS
    assert "PONG" in res.detail
    mock_client.ping.assert_called_once()
    mock_client.close.assert_called_once()


@patch("redis.Redis")
def test_redis_ping_failures(mock_redis_cls):
    import redis.exceptions

    # Connection error
    mock_client = MagicMock()
    mock_client.ping.side_effect = redis.exceptions.ConnectionError("Connection refused")
    mock_redis_cls.return_value = mock_client

    res = run_redis_ping_check("redis://127.0.0.1:6380/0", timeout=2.0)
    assert res.status == CheckStatus.FAIL
    assert "connection_refused" in res.detail


@patch("httpx.Client")
def test_api_health_success(mock_httpx_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "service": "Bot Chat API"}

    mock_instance = MagicMock()
    mock_instance.get.return_value = mock_resp
    mock_httpx_client.return_value.__enter__.return_value = mock_instance

    res = run_api_health_check("http://127.0.0.1:8002", timeout=2.0)
    assert res.status == CheckStatus.PASS
    assert "200 OK" in res.detail
    mock_instance.get.assert_called_once_with("http://127.0.0.1:8002/health")


@patch("httpx.Client")
def test_api_health_redirect_failure(mock_httpx_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 302

    mock_instance = MagicMock()
    mock_instance.get.return_value = mock_resp
    mock_httpx_client.return_value.__enter__.return_value = mock_instance

    res = run_api_health_check("http://127.0.0.1:8002", timeout=2.0)
    assert res.status == CheckStatus.FAIL
    assert "redirect" in res.detail


@patch("redis.Redis")
@patch("httpx.Client")
def test_no_network_on_blocked_preflight(mock_httpx, mock_redis, valid_qa_config, tmp_path):
    # Alterar APP_ENV para invalido para forçar status BLOCKED
    valid_qa_config["APP_ENV"] = "prd"
    env_file = tmp_path / ".env.qa"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in valid_qa_config.items()))

    report, exit_code = validate_environment(str(env_file), "http://127.0.0.1:8002")

    assert report.status == AggregatedStatus.BLOCKED
    assert exit_code == 2

    # Confirmar que NENHUMA chamada de rede foi realizada
    mock_redis.assert_not_called()
    mock_httpx.assert_not_called()

    # Confirmar que redis_ping e api_health foram marcados como NOT_EXECUTED
    redis_check = next(c for c in report.checks if c.name == "redis_ping")
    api_check = next(c for c in report.checks if c.name == "api_health")
    assert redis_check.status == CheckStatus.NOT_EXECUTED
    assert api_check.status == CheckStatus.NOT_EXECUTED


def test_main_cli_blocked(tmp_path, capsys):
    env_file = tmp_path / ".env.qa"
    env_file.write_text("APP_ENV=prd\n")

    exit_code = main(["--env-file", str(env_file)])
    assert exit_code == 2

    captured = capsys.readouterr()
    report_data = json.loads(captured.out)
    assert report_data["status"] == "BLOCKED"
