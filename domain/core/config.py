"""Domain-level configuration — reads env vars directly.

This config is used by domain/ code. It does NOT depend on app/core/config.py.
In Docker, env vars are injected. In local dev, env vars must be set or a .env
file must exist in the working directory (e.g. mcp_server/.env).
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_FILE = Path(__file__).resolve().parent.parent.parent / "mcp_server" / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PI Web API
    PI_WEB_API_BASE_URL: str = "http://10.247.224.39/piwebapi"
    PI_SERVER_NAME: str = "PIMS"
    PI_WEB_API_USERNAME: str | None = None
    PI_WEB_API_PASSWORD: str | None = None
    PI_WEB_API_VERIFY_SSL: bool = False

    # Math Tool
    # MATH_TOOL_TIMEOUT_SECONDS controls the READ timeout for Math Tool
    # HTTP calls. Connect/write/pool timeouts are hardcoded in the client
    # to 5s/10s/5s respectively.
    MATH_TOOL_BASE_URL: str = "http://math_tool:8001"
    MATH_TOOL_TIMEOUT_SECONDS: float = 120

    # Grafana / Loki
    GRAFANA_LOKI_QUERY_RANGE_URL: str = ""
    GRAFANA_BEARER_TOKEN: str = ""
    PIMS_STATUS_LOKI_QUERY: str = '{job="zabbix_proxy"}'
    PIMS_STATUS_LOOKBACK_MINUTES: int = 20
    PIMS_STATUS_LIMIT: int = 5000

    # Redis
    REDIS_URL: str = "redis://127.0.0.1:6379/2"
    CHAT_MEMORY_TTL_SECONDS: int = 604800
    CHAT_MEMORY_MAX_TURNS: int = 8

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text-v2-moe"

    # Qdrant
    QDRANT_URL: str = "http://10.247.179.197:6333"
    QDRANT_COLLECTION: str = "pi_web_api_guide"


settings = Settings()
