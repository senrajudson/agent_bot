import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

from domain.core.integration_settings import DomainIntegrationSettings

logger = logging.getLogger("mcp_server.config")


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

    REDIS_URL: str = "redis://127.0.0.1:6379/2"

    MATH_TOOL_BASE_URL: str = "http://math_tool:8001"
    MATH_TOOL_TIMEOUT_SECONDS: float = 120

    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8003

    # Agent Bot API — artifact upload
    AGENT_API_BASE_URL: str = "http://localhost:8002"
    AGENT_ARTIFACT_TOKEN: str | None = None
    AGENT_ARTIFACT_UPLOAD_TIMEOUT_SECONDS: float = 60.0
    AGENT_ARTIFACT_MAX_UPLOAD_BYTES: int = 104857600

    # Feature flag — generate_test_artifact_tool (referência / validação)
    ENABLE_TEST_ARTIFACT_TOOL: bool = False

    # Drive CSV export (opt-in, default false)
    ENABLE_DRIVE_CSV_EXPORT_TOOL: bool = False
    GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE: str | None = None
    GOOGLE_DRIVE_EXPORT_FOLDER_ID: str | None = None

    DRIVE_CSV_MAX_ROWS: int = 500
    DRIVE_CSV_MAX_COLUMNS: int = 50
    DRIVE_CSV_MAX_CELL_BYTES: int = 32768
    DRIVE_CSV_MAX_INPUT_BYTES: int = 5242880
    DRIVE_CSV_MAX_FILE_BYTES: int = 10485760
    DRIVE_CSV_UPLOAD_TIMEOUT_SECONDS: float = 60.0
    DRIVE_CSV_MAX_FILENAME_LENGTH: int = 180
    DRIVE_CSV_FORMULA_PROTECTION: bool = True

    # MCP Drive Artifact Delivery (feature flag, default false)
    ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY: bool = False

    MCP_ARTIFACT_MAX_ROWS: int = 1_000_000
    MCP_ARTIFACT_MAX_BYTES: int = 104_857_600
    MCP_ARTIFACT_MAX_COLUMNS: int = 50
    MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS: float = 120.0
    MCP_ARTIFACT_TEMP_DIR: str = "/tmp/agent_bot_mcp_artifacts"
    MCP_ARTIFACT_MANIFEST_MAX_BYTES: int = 8_192

    MCP_ARTIFACT_CSV_DELIMITER: str = ";"
    MCP_ARTIFACT_CSV_ENCODING: str = "utf-8-sig"

    MCP_ARTIFACT_FILENAME_ENVIRONMENT: str = "dev"

    MCP_INLINE_MAX_ROWS: int = 100
    MCP_INLINE_MAX_ITEMS: int = 100
    MCP_INLINE_MAX_BYTES: int = 65_536

    # generate_pi_tags_series_csv (feature flag, default false)
    ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV: bool = False
    MCP_SERIES_CSV_MAX_TAGS: int = 10
    MCP_SERIES_CSV_MAX_DAYS: int = 31
    MCP_SERIES_CSV_MIN_INTERVAL_SECONDS: int = 1
    MCP_SERIES_CSV_ERROR_MESSAGE_MAX_CHARS: int = 512
    MCP_SERIES_CSV_PUBLISH_TEMP_DIR: str = "/tmp/agent_bot_mcp_series_csv"

    # search_pi_points strict AND (feature flag, default false)
    ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND: bool = False
    MCP_SEARCH_PI_POINTS_INTERNAL_MAX_COUNT: int = 25
    MCP_SEARCH_PI_POINTS_MAX_VARIANTS: int = 4
    MCP_SEARCH_PI_POINTS_TIMEOUT_SECONDS: float = 30.0

    def to_domain_integration_settings(self) -> DomainIntegrationSettings:
        return DomainIntegrationSettings(
            PI_WEB_API_BASE_URL=self.PI_WEB_API_BASE_URL,
            PI_SERVER_NAME=self.PI_SERVER_NAME,
            PI_WEB_API_USERNAME=self.PI_WEB_API_USERNAME,
            PI_WEB_API_PASSWORD=self.PI_WEB_API_PASSWORD or "",
            PI_WEB_API_VERIFY_SSL=self.PI_WEB_API_VERIFY_SSL,
            MATH_TOOL_BASE_URL=self.MATH_TOOL_BASE_URL,
            MATH_TOOL_TIMEOUT_SECONDS=self.MATH_TOOL_TIMEOUT_SECONDS,
            REDIS_URL=self.REDIS_URL,
        )

    @model_validator(mode="after")
    def _validate_drive_csv(self) -> "Settings":
        if not self.ENABLE_DRIVE_CSV_EXPORT_TOOL:
            return self
        if not self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE:
            raise ValueError(
                "GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE obrigatório quando "
                "ENABLE_DRIVE_CSV_EXPORT_TOOL=true."
            )
        if not Path(self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE).is_file():
            raise ValueError(
                f"Credencial não encontrada: "
                f"{self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE}"
            )
        if not self.GOOGLE_DRIVE_EXPORT_FOLDER_ID:
            raise ValueError(
                "GOOGLE_DRIVE_EXPORT_FOLDER_ID obrigatório quando "
                "ENABLE_DRIVE_CSV_EXPORT_TOOL=true."
            )
        if self.DRIVE_CSV_MAX_ROWS <= 0 or self.DRIVE_CSV_MAX_COLUMNS <= 0:
            raise ValueError("Limites MAX_ROWS e MAX_COLUMNS devem ser positivos.")
        if self.DRIVE_CSV_MAX_CELL_BYTES <= 0:
            raise ValueError("MAX_CELL_BYTES deve ser positivo.")
        if self.DRIVE_CSV_MAX_INPUT_BYTES <= 0:
            raise ValueError("MAX_INPUT_BYTES deve ser positivo.")
        if self.DRIVE_CSV_MAX_FILE_BYTES <= 0:
            raise ValueError("MAX_FILE_BYTES deve ser positivo.")
        if self.DRIVE_CSV_MAX_INPUT_BYTES > self.DRIVE_CSV_MAX_FILE_BYTES:
            raise ValueError(
                "MAX_INPUT_BYTES não pode exceder MAX_FILE_BYTES."
            )
        if self.DRIVE_CSV_UPLOAD_TIMEOUT_SECONDS <= 0:
            raise ValueError("UPLOAD_TIMEOUT_SECONDS deve ser positivo.")
        if self.DRIVE_CSV_MAX_FILENAME_LENGTH <= 0:
            raise ValueError("MAX_FILENAME_LENGTH deve ser positivo.")
        return self

    @model_validator(mode="after")
    def _validate_drive_artifact_delivery(self) -> "Settings":
        if not self.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY:
            return self
        if not self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE:
            raise ValueError(
                "GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE obrigatório quando "
                "ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY=true."
            )
        if not Path(self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE).is_file():
            raise ValueError(
                f"Credencial não encontrada: "
                f"{self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE}"
            )
        if not self.GOOGLE_DRIVE_EXPORT_FOLDER_ID:
            raise ValueError(
                "GOOGLE_DRIVE_EXPORT_FOLDER_ID obrigatório quando "
                "ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY=true."
            )
        if not Path(self.MCP_ARTIFACT_TEMP_DIR).is_dir() and not Path(self.MCP_ARTIFACT_TEMP_DIR).parent.is_dir():
            raise ValueError(
                f"MCP_ARTIFACT_TEMP_DIR não acessível: {self.MCP_ARTIFACT_TEMP_DIR}"
            )
        if self.MCP_ARTIFACT_MAX_ROWS <= 0:
            raise ValueError("MCP_ARTIFACT_MAX_ROWS deve ser positivo.")
        if self.MCP_ARTIFACT_MAX_BYTES <= 0:
            raise ValueError("MCP_ARTIFACT_MAX_BYTES deve ser positivo.")
        if self.MCP_ARTIFACT_MAX_COLUMNS <= 0:
            raise ValueError("MCP_ARTIFACT_MAX_COLUMNS deve ser positivo.")
        if self.MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS <= 0:
            raise ValueError("MCP_ARTIFACT_UPLOAD_TIMEOUT_SECONDS deve ser positivo.")
        if self.MCP_ARTIFACT_MANIFEST_MAX_BYTES <= 0:
            raise ValueError("MCP_ARTIFACT_MANIFEST_MAX_BYTES deve ser positivo.")
        if self.MCP_INLINE_MAX_BYTES <= 0:
            raise ValueError("MCP_INLINE_MAX_BYTES deve ser positivo.")
        if self.MCP_INLINE_MAX_BYTES > self.MCP_ARTIFACT_MAX_BYTES:
            raise ValueError(
                "MCP_INLINE_MAX_BYTES não pode exceder MCP_ARTIFACT_MAX_BYTES."
            )
        return self

    @model_validator(mode="after")
    def _validate_generate_pi_tags_series_csv(self) -> "Settings":
        if not self.ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV:
            return self
        if not self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE:
            raise ValueError(
                "GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE obrigatório quando "
                "ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=true."
            )
        if not Path(self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE).is_file():
            raise ValueError(
                f"Credencial não encontrada: {self.GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE}"
            )
        if not self.GOOGLE_DRIVE_EXPORT_FOLDER_ID:
            raise ValueError(
                "GOOGLE_DRIVE_EXPORT_FOLDER_ID obrigatório quando "
                "ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=true."
            )
        if self.MCP_SERIES_CSV_MAX_TAGS <= 0:
            raise ValueError("MCP_SERIES_CSV_MAX_TAGS deve ser positivo.")
        if self.MCP_SERIES_CSV_MAX_DAYS <= 0:
            raise ValueError("MCP_SERIES_CSV_MAX_DAYS deve ser positivo.")
        if self.MCP_SERIES_CSV_MIN_INTERVAL_SECONDS <= 0:
            raise ValueError("MCP_SERIES_CSV_MIN_INTERVAL_SECONDS deve ser positivo.")
        if not Path(self.MCP_SERIES_CSV_PUBLISH_TEMP_DIR).parent.is_dir() and \
           not Path(self.MCP_SERIES_CSV_PUBLISH_TEMP_DIR).is_dir():
            raise ValueError(
                f"MCP_SERIES_CSV_PUBLISH_TEMP_DIR não acessível: {self.MCP_SERIES_CSV_PUBLISH_TEMP_DIR}"
            )
        return self

    @model_validator(mode="after")
    def _validate_test_artifact_tool(self) -> "Settings":
        if not self.ENABLE_TEST_ARTIFACT_TOOL:
            return self
        if not self.AGENT_ARTIFACT_TOKEN:
            raise ValueError(
                "ENABLE_TEST_ARTIFACT_TOOL=true requires AGENT_ARTIFACT_TOKEN."
            )
        if not self.AGENT_API_BASE_URL:
            raise ValueError(
                "ENABLE_TEST_ARTIFACT_TOOL=true requires AGENT_API_BASE_URL."
            )
        return self

    @model_validator(mode="after")
    def _validate_search_pi_points_strict_and(self) -> "Settings":
        if not self.ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND:
            return self
        if self.MCP_SEARCH_PI_POINTS_INTERNAL_MAX_COUNT < 5:
            raise ValueError(
                "MCP_SEARCH_PI_POINTS_INTERNAL_MAX_COUNT deve ser >= 5."
            )
        if self.MCP_SEARCH_PI_POINTS_MAX_VARIANTS not in {1, 2, 3, 4}:
            raise ValueError(
                "MCP_SEARCH_PI_POINTS_MAX_VARIANTS deve estar entre 1 e 4."
            )
        if self.MCP_SEARCH_PI_POINTS_TIMEOUT_SECONDS <= 0:
            raise ValueError(
                "MCP_SEARCH_PI_POINTS_TIMEOUT_SECONDS deve ser positivo."
            )
        return self

    def log_effective_config(self) -> None:
        logger.info(
            "Effective config: "
            "ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY=%s "
            "ENABLE_DRIVE_CSV_EXPORT_TOOL=%s "
            "ENABLE_TEST_ARTIFACT_TOOL=%s "
            "ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=%s "
            "ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND=%s "
            "MCP_PORT=%s",
            self.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY,
            self.ENABLE_DRIVE_CSV_EXPORT_TOOL,
            self.ENABLE_TEST_ARTIFACT_TOOL,
            self.ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV,
            self.ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND,
            self.MCP_PORT,
        )


settings = Settings()
