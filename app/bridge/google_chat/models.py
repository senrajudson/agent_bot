from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GoogleChatUser:
    name: str = ""
    display_name: str = ""
    email: str = ""
    type: str = ""
    domain_id: str = ""


@dataclass(slots=True)
class GoogleChatAttachment:
    name: str = ""
    content_name: str = ""
    content_type: str = ""
    resource_name: str = ""
    source: str = ""
    thumbnail_uri: str = ""
    download_uri: str = ""

    @property
    def is_uploaded_content(self) -> bool:
        return self.source.upper() == "UPLOADED_CONTENT"

    @property
    def is_image(self) -> bool:
        return self.content_type.lower().startswith("image/")

    @property
    def can_download_with_chat_api(self) -> bool:
        return self.is_uploaded_content and bool(self.resource_name)


@dataclass(slots=True)
class GoogleChatIncomingMessage:
    pubsub_message_id: str = ""
    event_type: str = "UNKNOWN"

    space_name: str = ""
    space_type: str = ""
    space_threading_state: str = ""

    message_name: str = ""
    message_text: str = ""
    argument_text: str = ""
    formatted_text: str = ""

    thread_name: str = ""

    create_time: str = ""
    event_time: str = ""

    user: GoogleChatUser = field(default_factory=GoogleChatUser)
    attachments: list[GoogleChatAttachment] = field(default_factory=list)

    user_locale: str = ""
    time_zone_id: str = ""
    time_zone_offset: int | None = None

    raw_event: dict[str, Any] = field(default_factory=dict)

    @property
    def is_from_bot(self) -> bool:
        return self.user.type.upper() == "BOT"

    @property
    def is_from_human(self) -> bool:
        return self.user.type.upper() == "HUMAN"

    @property
    def clean_text(self) -> str:
        return (self.argument_text or self.message_text or self.formatted_text or "").strip()

    @property
    def has_text(self) -> bool:
        return bool(self.clean_text)

    @property
    def has_attachments(self) -> bool:
        return bool(self.attachments)

    @property
    def has_image_attachments(self) -> bool:
        return any(attachment.is_image for attachment in self.attachments)

    @property
    def can_process(self) -> bool:
        return (
            self.event_type == "MESSAGE"
            and (self.has_text or self.has_image_attachments)
            and bool(self.space_name)
            and bool(self.message_name)
            and not self.is_from_bot
        )

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "pubsub_message_id": self.pubsub_message_id,
            "event_type": self.event_type,
            "space_name": self.space_name,
            "thread_name": self.thread_name,
            "message_name": self.message_name,
            "message_text": self.clean_text,
            "user_name": self.user.name,
            "user_display_name": self.user.display_name,
            "user_email": self.user.email,
            "user_type": self.user.type,
            "attachments_count": len(self.attachments),
            "image_attachments_count": sum(1 for item in self.attachments if item.is_image),
            "can_process": self.can_process,
        }