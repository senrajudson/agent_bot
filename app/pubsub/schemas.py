"""
Pub/Sub message schemas.

Incoming: published to the agent's incoming topic (e.g. by a Google Chat bridge).
Outgoing: published by the agent to the response topic.
"""

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.schemas.chat import ChatImage


DEFAULT_TIMEZONE = "America/Sao_Paulo"


class IncomingMessage(BaseModel):
    request_id: str = Field(..., min_length=1)
    user_id: str | None = None
    conversation_id: str | None = None
    message: str = ""
    images: list[ChatImage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutgoingMessage(BaseModel):
    request_id: str
    type: Literal["response", "error"] = "response"
    content: str
    categoria: str | None = None
    next_action: str | None = None
    has_image: bool = False
    tags_encontradas: list[str] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat(timespec="seconds")
    )
