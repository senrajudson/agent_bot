from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    API_NAME: str = "Bot Chat API"
    API_PORT: int = 8002

    LLM_PROVIDER: str = "ollama"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4:e4b"

    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODEL: str | None = None

    OPENAI_COMPATIBLE_API_KEY: str | None = None
    OPENAI_COMPATIBLE_BASE_URL: str | None = None
    OPENAI_COMPATIBLE_MODEL: str | None = None

    PI_WEB_API_BASE_URL: str = "http://10.247.224.39/piwebapi"
    PI_SERVER_NAME: str = "PIMS"
    PI_WEB_API_USERNAME: str | None = None
    PI_WEB_API_PASSWORD: str | None = None
    PI_WEB_API_VERIFY_SSL: bool = False

    GRAFANA_LOKI_QUERY_RANGE_URL: str
    GRAFANA_BEARER_TOKEN: str = "SEU_TOKEN_DO_GRAFANA"
    PIMS_STATUS_LOKI_QUERY: str = '{job="zabbix_proxy"}'
    PIMS_STATUS_LOOKBACK_MINUTES: int = 20
    PIMS_STATUS_LIMIT: int = 5000

    PHOENIX_ENABLED: bool = False
    PHOENIX_PROJECT_NAME: str = "pi-chat-api"
    PHOENIX_COLLECTOR_ENDPOINT: str = "http://localhost:6006/v1/traces"
    PHOENIX_PROTOCOL: str = "http/protobuf"

    MATH_TOOL_BASE_URL: str = "http://math_tool:8001"
    MATH_TOOL_TIMEOUT_SECONDS: float = 120

    # Embedding provider: "nomic" (legado) or "gemini"
    EMBEDDING_PROVIDER: str = "nomic"
    EMBEDDING_MODEL: str | None = None
    EMBEDDING_VECTOR_SIZE: int = 768
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_TIMEOUT_SECONDS: float = 60.0
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"

    QDRANT_URL: str = "http://10.247.179.197:6333"
    QDRANT_COLLECTION: str = "pi_web_api_guide"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text-v2-moe"

    REDIS_URL: str = "redis://127.0.0.1:6379/2"
    CHAT_MEMORY_TTL_SECONDS: int = 604800
    CHAT_MEMORY_MAX_TURNS: int = 8

    MCP_SERVER_URL: str = "http://localhost:8005/mcp"

    # Event Store backend: "memory" (default), "redis_streams", or "postgres"
    EVENT_STORE_BACKEND: str = "memory"
    EVENT_STORE_POSTGRES_DSN: str | None = None

    # Feature flag: gate for EDD (Event Driven Design) Postgres integration.
    # Default False preserves current runtime behavior (InMemoryEventStore).
    EVENT_DRIVEN_ENABLED: bool = False

    # Artifact layer
    AGENT_ARTIFACT_TTL_SECONDS: int = 3600
    AGENT_ARTIFACTS_BASE_DIR: str = "/tmp/agent_bot_artifacts"
    AGENT_ARTIFACTS_PUBLIC_PATH_PREFIX: str = "/artifacts"
    AGENT_ARTIFACTS_TOKEN: str | None = None
    AGENT_ARTIFACT_MAX_UPLOAD_BYTES: int = 104857600
    AGENT_ARTIFACT_ALLOWED_MIME_TYPES: str = "text/plain,text/csv,application/json,application/octet-stream"
    AGENT_ARTIFACT_BLOCKED_EXTENSIONS: str = ".exe,.bat,.sh,.dll,.cmd,.com,.scr"

    # Test artifact tool (feature flag for QA validation)
    ENABLE_TEST_ARTIFACT_TOOL: bool = False

    # Drive CSV export (opt-in, default false)
    ENABLE_DRIVE_CSV_EXPORT_TOOL: bool = False


settings = Settings()