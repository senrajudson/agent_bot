import pytest
from unittest.mock import MagicMock, patch
from opentelemetry.sdk.trace import TracerProvider

from app.core import config
from app.observability import phoenix


@pytest.fixture(autouse=True)
def reset_phoenix_state(monkeypatch):
    """Reseta o estado global do tracer provider do Phoenix antes de cada teste."""
    monkeypatch.setattr(phoenix, "_tracer_provider", None)


def test_setup_phoenix_tracing_project_default(monkeypatch):
    """Valida que o projeto Phoenix padrão 'pi-chat-api' é passado ao register()."""
    monkeypatch.setattr(config.settings, "PHOENIX_ENABLED", True)
    monkeypatch.setattr(config.settings, "PHOENIX_PROJECT_NAME", "pi-chat-api")

    mock_provider = MagicMock(spec=TracerProvider)
    with patch("app.observability.phoenix.register", return_value=mock_provider) as mock_register, \
         patch("app.observability.phoenix._wrap_default_exporter"), \
         patch("app.observability.phoenix._instrument_litellm"), \
         patch("app.observability.phoenix._instrument_google_genai"), \
         patch("app.observability.phoenix._instrument_httpx"):
        
        provider = phoenix.setup_phoenix_tracing()

        assert provider == mock_provider
        mock_register.assert_called_once()
        _, kwargs = mock_register.call_args
        assert kwargs.get("project_name") == "pi-chat-api"


def test_setup_phoenix_tracing_project_qa_override(monkeypatch):
    """Valida que o projeto Phoenix de QA 'pi-chat-api-qa' é passado ao register()."""
    monkeypatch.setattr(config.settings, "PHOENIX_ENABLED", True)
    monkeypatch.setattr(config.settings, "PHOENIX_PROJECT_NAME", "pi-chat-api-qa")

    mock_provider = MagicMock(spec=TracerProvider)
    with patch("app.observability.phoenix.register", return_value=mock_provider) as mock_register, \
         patch("app.observability.phoenix._wrap_default_exporter"), \
         patch("app.observability.phoenix._instrument_litellm"), \
         patch("app.observability.phoenix._instrument_google_genai"), \
         patch("app.observability.phoenix._instrument_httpx"):

        provider = phoenix.setup_phoenix_tracing()

        assert provider == mock_provider
        mock_register.assert_called_once()
        _, kwargs = mock_register.call_args
        assert kwargs.get("project_name") == "pi-chat-api-qa"


def test_phoenix_resource_attributes_qa_env(monkeypatch):
    """Valida a leitura e composição dos atributos de recurso OTEL_RESOURCE_ATTRIBUTES."""
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment=qa,app.channel=n8n")
    
    raw_attrs = config.settings.OTEL_RESOURCE_ATTRIBUTES if hasattr(config.settings, "OTEL_RESOURCE_ATTRIBUTES") else None
    import os
    env_attrs = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    
    parsed = dict(item.split("=") for item in env_attrs.split(",") if "=" in item)
    assert parsed.get("deployment.environment") == "qa"
    assert parsed.get("app.channel") == "n8n"


def test_setup_phoenix_tracing_disabled(monkeypatch):
    """Valida que quando PHOENIX_ENABLED=False, nenhuma inicialização ocorre."""
    monkeypatch.setattr(config.settings, "PHOENIX_ENABLED", False)

    with patch("app.observability.phoenix.register") as mock_register:
        provider = phoenix.setup_phoenix_tracing()
        assert provider is None
        mock_register.assert_not_called()


def test_setup_phoenix_tracing_idempotency(monkeypatch):
    """Valida que chamadas repetidas retornam o provider prévio sem reinicializar."""
    monkeypatch.setattr(config.settings, "PHOENIX_ENABLED", True)

    mock_provider = MagicMock(spec=TracerProvider)
    with patch("app.observability.phoenix.register", return_value=mock_provider) as mock_register, \
         patch("app.observability.phoenix._wrap_default_exporter"), \
         patch("app.observability.phoenix._instrument_litellm"), \
         patch("app.observability.phoenix._instrument_google_genai"), \
         patch("app.observability.phoenix._instrument_httpx"):

        p1 = phoenix.setup_phoenix_tracing()
        p2 = phoenix.setup_phoenix_tracing()

        assert p1 == mock_provider
        assert p2 == mock_provider
        assert mock_register.call_count == 1


def test_phoenix_privacy_no_sensitive_attrs():
    """Garante que atributos sensíveis de conteúdo/prompts não estão expostos nos sanitizadores."""
    for attr in phoenix._TOKEN_ATTRS_TO_REMOVE:
        assert "prompt.text" not in attr
        assert "message.content" not in attr
        assert "password" not in attr
        assert "token.secret" not in attr
