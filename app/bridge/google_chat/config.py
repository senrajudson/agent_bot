from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GoogleChatBridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "app/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    google_cloud_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")

    google_chat_subscription: str = Field(
        default="",
        alias="GOOGLE_CHAT_SUBSCRIPTION",
    )

    google_application_credentials: str = Field(
        default="./secrets/chat-bot-secret.json",
        alias="GOOGLE_APPLICATION_CREDENTIALS",
    )

    google_chat_scopes_raw: str = Field(
        default=(
            "https://www.googleapis.com/auth/chat.bot "
            "https://www.googleapis.com/auth/chat.messages.readonly"
        ),
        alias="GOOGLE_CHAT_SCOPES",
    )

    agent_internal_url: str = Field(
        default="http://localhost:8002/chat",
        alias="AGENT_INTERNAL_URL",
    )

    google_chat_send_thinking_message: bool = Field(
        default=True,
        alias="GOOGLE_CHAT_SEND_THINKING_MESSAGE",
    )

    google_chat_thinking_text: str = Field(
        default="Um momento...",
        alias="GOOGLE_CHAT_THINKING_TEXT",
    )

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    google_chat_dedupe_ttl_seconds: int = Field(
        default=86400,
        alias="GOOGLE_CHAT_DEDUPE_TTL_SECONDS",
    )

    # Chat attachments
    enable_chat_attachments: bool = Field(
        default=False,
        alias="ENABLE_CHAT_ATTACHMENTS",
    )

    agent_artifact_base_url: str = Field(
        default="http://localhost:8002/artifacts",
        alias="AGENT_ARTIFACT_BASE_URL",
    )

    agent_artifact_token: str | None = Field(
        default=None,
        alias="AGENT_ARTIFACT_TOKEN",
    )

    google_chat_max_attachments_per_message: int = Field(
        default=3,
        alias="GOOGLE_CHAT_MAX_ATTACHMENTS_PER_MESSAGE",
    )

    bridge_artifact_timeout_seconds: float = Field(
        default=30.0,
        alias="BRIDGE_ARTIFACT_TIMEOUT_SECONDS",
    )

    bridge_artifact_max_bytes: int = Field(
        default=26214400,
        alias="BRIDGE_ARTIFACT_MAX_BYTES",
    )

    bridge_artifact_max_total_bytes: int = Field(
        default=52428800,
        alias="BRIDGE_ARTIFACT_MAX_TOTAL_BYTES",
    )

    @property
    def google_chat_scopes(self) -> list[str]:
        return [
            scope.strip()
            for scope in self.google_chat_scopes_raw.split()
            if scope.strip()
        ]

    @property
    def service_account_path(self) -> Path:
        return Path(self.google_application_credentials).expanduser().resolve()

    def validate_google_chat_config(self) -> None:
        errors: list[str] = []

        if not self.google_cloud_project:
            errors.append("GOOGLE_CLOUD_PROJECT não configurado.")

        if not self.google_chat_subscription:
            errors.append("GOOGLE_CHAT_SUBSCRIPTION não configurado.")

        if not self.agent_internal_url:
            errors.append("AGENT_INTERNAL_URL não configurado.")

        if not self.google_chat_scopes:
            errors.append("GOOGLE_CHAT_SCOPES não configurado.")

        if not self.service_account_path.exists():
            errors.append(
                f"Arquivo da Service Account não encontrado: {self.service_account_path}"
            )

        if errors:
            raise RuntimeError("Configuração inválida:\n- " + "\n- ".join(errors))


@lru_cache(maxsize=1)
def get_google_chat_bridge_settings() -> GoogleChatBridgeSettings:
    return GoogleChatBridgeSettings()