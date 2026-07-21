from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PI_WEB_API_BASE_URL: str = "http://10.247.224.39/piwebapi"
    PI_SERVER_NAME: str = "PIMS"
    PI_WEB_API_USERNAME: str | None = None
    PI_WEB_API_PASSWORD: str | None = None
    PI_WEB_API_VERIFY_SSL: bool = False

    GRAFANA_LOKI_QUERY_RANGE_URL: str = ""
    GRAFANA_BEARER_TOKEN: str = ""
    PIMS_STATUS_LOKI_QUERY: str = '{job="zabbix_proxy"}'
    PIMS_STATUS_LOOKBACK_MINUTES: int = 20
    PIMS_STATUS_LIMIT: int = 5000

    MATH_TOOL_BASE_URL: str = "http://math_tool:8001"
    MATH_TOOL_TIMEOUT_SECONDS: float = 120

    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8003

    # Agent Bot API — artifact upload
    AGENT_API_BASE_URL: str = "http://localhost:8002"
    AGENT_ARTIFACTS_TOKEN: str | None = None
    AGENT_ARTIFACT_UPLOAD_TIMEOUT_SECONDS: float = 60.0
    AGENT_ARTIFACT_MAX_UPLOAD_BYTES: int = 104857600

    # Feature flag — generate_test_artifact_tool (referência / validação)
    ENABLE_TEST_ARTIFACT_TOOL: bool = False


settings = Settings()
