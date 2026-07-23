from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


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


settings = Settings()
