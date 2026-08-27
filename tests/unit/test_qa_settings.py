import pytest
from app.core.config import Settings
from app.domain.value_objects import ConversationId
from app.services.chat_memory_service import _memory_key, _dedupe_key


def test_settings_qa_defaults(monkeypatch):
    """Valida os valores padrão de APP_ENV e REDIS_KEY_PREFIX."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("REDIS_KEY_PREFIX", raising=False)
    s = Settings(_env_file=None)
    assert s.APP_ENV == "local"
    assert s.REDIS_KEY_PREFIX == "pi_chat:memory"
    assert s.REDIS_URL == "redis://127.0.0.1:6379/2"


def test_settings_qa_overrides(monkeypatch):
    """Valida a sobrescrita de APP_ENV, REDIS_KEY_PREFIX e REDIS_URL por variáveis de ambiente."""
    monkeypatch.setenv("APP_ENV", "qa")
    monkeypatch.setenv("REDIS_KEY_PREFIX", "pi_chat:qa:memory")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6380/0")

    s = Settings()
    assert s.APP_ENV == "qa"
    assert s.REDIS_KEY_PREFIX == "pi_chat:qa:memory"
    assert s.REDIS_URL == "redis://127.0.0.1:6380/0"


def test_chat_memory_service_key_formatting_legacy(monkeypatch):
    """Valida a formação exata da chave com o prefixo legado padrao."""
    from app.core import config
    monkeypatch.setattr(config.settings, "REDIS_KEY_PREFIX", "pi_chat:memory")

    cid = ConversationId.from_user_id("user123")
    assert _memory_key(cid) == "pi_chat:memory:user123:turns"
    assert _dedupe_key(cid, "evt001") == "pi_chat:memory:user123:dedupe:evt001"


def test_chat_memory_service_key_formatting_qa(monkeypatch):
    """Valida a formação exata da chave no ambiente QA com o novo prefixo."""
    from app.core import config
    monkeypatch.setattr(config.settings, "REDIS_KEY_PREFIX", "pi_chat:qa:memory")

    cid = ConversationId.from_user_id("user123")
    assert _memory_key(cid) == "pi_chat:qa:memory:user123:turns"
    assert _dedupe_key(cid, "evt001") == "pi_chat:qa:memory:user123:dedupe:evt001"


def test_artifact_settings_api_defaults(monkeypatch):
    """Valida o diretório de artefatos padrão da API."""
    monkeypatch.delenv("AGENT_ARTIFACTS_BASE_DIR", raising=False)
    s = Settings(_env_file=None)
    assert s.AGENT_ARTIFACTS_BASE_DIR == "/tmp/agent_bot_artifacts"


def test_artifact_settings_api_qa_override(monkeypatch):
    """Valida o override do diretório de artefatos da API em QA."""
    monkeypatch.setenv("AGENT_ARTIFACTS_BASE_DIR", "/tmp/agent_bot_qa/api_artifacts")
    s = Settings()
    assert s.AGENT_ARTIFACTS_BASE_DIR == "/tmp/agent_bot_qa/api_artifacts"


def test_artifact_settings_mcp_defaults(monkeypatch):
    """Valida os diretórios padrão de relatórios e séries CSV do MCP Server."""
    from mcp_server.core.config import Settings as McpSettings
    monkeypatch.delenv("MCP_ARTIFACT_TEMP_DIR", raising=False)
    monkeypatch.delenv("MCP_SERIES_CSV_PUBLISH_TEMP_DIR", raising=False)
    mcp_s = McpSettings(_env_file=None)
    assert mcp_s.MCP_ARTIFACT_TEMP_DIR == "/tmp/agent_bot_mcp_artifacts"
    assert mcp_s.MCP_SERIES_CSV_PUBLISH_TEMP_DIR == "/tmp/agent_bot_mcp_series_csv"


def test_artifact_settings_mcp_qa_overrides(monkeypatch, tmp_path):
    """Valida os overrides dos diretórios do MCP Server em QA."""
    from mcp_server.core.config import Settings as McpSettings
    qa_dir = tmp_path / "agent_bot_qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    mcp_art = str(qa_dir / "mcp_artifacts")
    mcp_csv = str(qa_dir / "mcp_series_csv")

    monkeypatch.setenv("MCP_ARTIFACT_TEMP_DIR", mcp_art)
    monkeypatch.setenv("MCP_SERIES_CSV_PUBLISH_TEMP_DIR", mcp_csv)
    mcp_s = McpSettings()
    assert mcp_s.MCP_ARTIFACT_TEMP_DIR == mcp_art
    assert mcp_s.MCP_SERIES_CSV_PUBLISH_TEMP_DIR == mcp_csv


def test_artifact_settings_mcp_qa_tmp_root(monkeypatch):
    """Valida os overrides exatos apontando para /tmp/agent_bot_qa/."""
    from pathlib import Path
    from mcp_server.core.config import Settings as McpSettings
    Path("/tmp/agent_bot_qa").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("MCP_ARTIFACT_TEMP_DIR", "/tmp/agent_bot_qa/mcp_artifacts")
    monkeypatch.setenv("MCP_SERIES_CSV_PUBLISH_TEMP_DIR", "/tmp/agent_bot_qa/mcp_series_csv")
    mcp_s = McpSettings()
    assert mcp_s.MCP_ARTIFACT_TEMP_DIR == "/tmp/agent_bot_qa/mcp_artifacts"
    assert mcp_s.MCP_SERIES_CSV_PUBLISH_TEMP_DIR == "/tmp/agent_bot_qa/mcp_series_csv"


def test_tracing_settings_default(monkeypatch):
    """Valida o projeto Phoenix padrão sem overrides de QA."""
    monkeypatch.delenv("PHOENIX_PROJECT_NAME", raising=False)
    s = Settings(_env_file=None)
    assert s.PHOENIX_PROJECT_NAME == "pi-chat-api"


def test_tracing_settings_qa_override(monkeypatch):
    """Valida a alteração do projeto Phoenix e atributos de recurso via ambiente QA."""
    monkeypatch.setenv("PHOENIX_PROJECT_NAME", "pi-chat-api-qa")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment=qa,app.channel=n8n")
    s = Settings()
    assert s.PHOENIX_PROJECT_NAME == "pi-chat-api-qa"


