from __future__ import annotations

from typing import Any

from app.bridge.google_chat.models import (
    GoogleChatAttachment,
    GoogleChatIncomingMessage,
    GoogleChatUser,
)


def parse_google_chat_event(data: dict[str, Any]) -> GoogleChatIncomingMessage:
    event = _extract_event(data)

    common_event_object = _as_dict(event.get("commonEventObject"))
    chat = _as_dict(event.get("chat"))
    message_payload = _as_dict(chat.get("messagePayload"))

    message = _as_dict(message_payload.get("message"))
    space = _as_dict(message_payload.get("space")) or _as_dict(message.get("space"))
    thread = _as_dict(message.get("thread"))

    sender = _as_dict(message.get("sender")) or _as_dict(chat.get("user"))

    time_zone = _as_dict(common_event_object.get("timeZone"))

    event_type = _detect_event_type(event=event, message_payload=message_payload)

    attachments = _parse_attachments(message)

    return GoogleChatIncomingMessage(
        pubsub_message_id=str(data.get("pubsubMessageId", "") or ""),
        event_type=event_type,
        space_name=str(space.get("name", "") or ""),
        space_type=str(space.get("type", "") or space.get("spaceType", "") or ""),
        space_threading_state=str(space.get("spaceThreadingState", "") or ""),
        message_name=str(message.get("name", "") or ""),
        message_text=str(message.get("text", "") or ""),
        argument_text=str(message.get("argumentText", "") or ""),
        formatted_text=str(message.get("formattedText", "") or ""),
        thread_name=str(thread.get("name", "") or ""),
        create_time=str(message.get("createTime", "") or ""),
        event_time=str(chat.get("eventTime", "") or ""),
        user=GoogleChatUser(
            name=str(sender.get("name", "") or ""),
            display_name=str(sender.get("displayName", "") or ""),
            email=str(sender.get("email", "") or ""),
            type=str(sender.get("type", "") or ""),
            domain_id=str(sender.get("domainId", "") or ""),
        ),
        attachments=attachments,
        user_locale=str(common_event_object.get("userLocale", "") or ""),
        time_zone_id=str(time_zone.get("id", "") or ""),
        time_zone_offset=_parse_optional_int(time_zone.get("offset")),
        raw_event=event,
    )


def _parse_attachments(message: dict[str, Any]) -> list[GoogleChatAttachment]:
    raw_attachments = message.get("attachment")

    if raw_attachments is None:
        raw_attachments = message.get("attachments")

    if not isinstance(raw_attachments, list):
        return []

    parsed_attachments: list[GoogleChatAttachment] = []

    for raw_attachment in raw_attachments:
        attachment = _as_dict(raw_attachment)
        attachment_data_ref = _as_dict(attachment.get("attachmentDataRef"))

        parsed_attachments.append(
            GoogleChatAttachment(
                name=str(attachment.get("name", "") or ""),
                content_name=str(attachment.get("contentName", "") or ""),
                content_type=str(attachment.get("contentType", "") or ""),
                resource_name=str(attachment_data_ref.get("resourceName", "") or ""),
                source=str(attachment.get("source", "") or ""),
                thumbnail_uri=str(attachment.get("thumbnailUri", "") or ""),
                download_uri=str(attachment.get("downloadUri", "") or ""),
            )
        )

    return parsed_attachments


def _extract_event(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    payload = data.get("payload")

    if isinstance(payload, dict) and ("chat" in payload or "commonEventObject" in payload):
        return payload

    if "chat" in data or "commonEventObject" in data:
        return data

    return {}


def _detect_event_type(
    event: dict[str, Any],
    message_payload: dict[str, Any],
) -> str:
    explicit_type = (
        event.get("type")
        or event.get("eventType")
        or message_payload.get("eventType")
        or message_payload.get("type")
    )

    if explicit_type:
        return str(explicit_type).upper()

    if message_payload.get("message"):
        return "MESSAGE"

    if message_payload.get("space"):
        return "SPACE_EVENT"

    return "UNKNOWN"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    return {}


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None