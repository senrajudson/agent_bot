# Google Chat Bridge — Complete Technical Reference

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture & Message Flow](#2-architecture--message-flow)
3. [Module Reference](#3-module-reference)
   - 3.1 [config.py](#31-configpy)
   - 3.2 [models.py](#32-modelspy)
   - 3.3 [parser.py](#33-parserpy)
   - 3.4 [pubsub_subscriber.py](#34-pubsub_subscriberpy)
   - 3.5 [media_downloader.py](#35-media_downloaderpy)
   - 3.6 [chat_client.py](#36-chat_clientpy)
   - 3.7 [agent_adapter.py](#37-agent_adapterpy)
   - 3.8 [dedupe_store.py](#38-dedupe_storepy)
   - 3.9 [worker.py](#39-workerpy)
4. [Test Scripts](#4-test-scripts)
   - 4.1 [test_download_image.py](#41-test_download_imagepy)
   - 4.2 [test_send_message.py](#42-test_send_messagepy)
5. [Docker Deployment](#5-docker-deployment)
6. [Environment Variables Reference](#6-environment-variables-reference)
7. [Error Handling & Edge Cases](#7-error-handling--edge-cases)

---

## 1. Overview

The **Google Chat Bridge** is an integration adapter module located at `app/bridge/google_chat/`. It connects the Agent Bot conversational API to Google Chat as a messaging frontend, allowing users to interact with the PI System agent directly from Google Chat spaces.

The bridge is **not** the GoF Bridge design pattern. It is a **domain-specific integration bridge** that acts as a bidirectional translator between two systems:

- **Inbound**: Listens for user messages from Google Chat via a Google Cloud Pub/Sub subscription
- **Outbound**: Sends the agent's responses back to the Google Chat space as reply messages

### Key Capabilities

- Receives messages asynchronously via Pub/Sub push/pull subscription
- Parses Google Chat event payloads into structured Python objects
- Downloads image attachments (PNG, JPEG, WEBP) for OCR processing
- Deduplicates messages using Redis (with in-memory fallback)
- Sends a "thinking" placeholder message while processing, then updates it with the final answer
- Gracefully handles errors without causing infinite retry loops

### Directory Structure

```
app/bridge/
├── __init__.py
└── google_chat/
    ├── __init__.py
    ├── config.py                # Pydantic settings and validation
    ├── models.py                # Dataclasses for parsed events
    ├── parser.py                # Raw Pub/Sub payload parser
    ├── pubsub_subscriber.py     # Pub/Sub subscription client
    ├── media_downloader.py      # Image attachment downloader
    ├── chat_client.py           # Google Chat API client
    ├── agent_adapter.py         # HTTP adapter to Agent Bot /chat
    ├── dedupe_store.py          # Redis/in-memory deduplication
    ├── worker.py                # Main orchestrator (entry point)
    ├── test_download_image.py   # Manual test: download images
    └── test_send_message.py     # Manual test: send message
```

---

## 2. Architecture & Message Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Google Chat User                             │
│                     sends message / image                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│               Google Cloud Pub/Sub                                  │
│          (subscription: GOOGLE_CHAT_SUBSCRIPTION)                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  message received
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PubSubSubscriber                                  │
│           decode_message() → raw JSON payload                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Parser                                        │
│       parse_google_chat_event() → GoogleChatIncomingMessage          │
│       extracts: user, text, attachments, space, thread, timezone     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    can_process? check                                │
│  Must be: MESSAGE event, has text or images, from human, has space   │
│  If no → ACK + skip (or NACK in test mode)                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ yes
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DedupeStore                                     │
│  try_start() → "started" | "duplicate_done" | "duplicate_processing"│
│  Uses Redis SET NX with TTL (processing key) + done key (24h TTL)   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ started
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  ChatClient.send_thinking()                          │
│  Posts "Um momento..." placeholder to Google Chat space              │
│  Returns thinking_message_name for later update                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  MediaDownloader                                     │
│  download_images_from_event() → list[DownloadedGoogleChatImage]      │
│  Downloads via Chat API media().download_media(), max 4 images,      │
│  max 10 MB each, PNG/JPEG/WEBP only, base64-encoded                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AgentAdapter                                    │
│  ask() → HTTP POST to AGENT_INTERNAL_URL (/chat)                    │
│  Payload: { message, user_id, images[] }                             │
│  Extracts answer from JSON response                                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ answer string
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  ChatClient.update_text()                            │
│  Patches the "thinking" message with the final answer                │
│  (or send_text() if no thinking message was sent)                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  DedupeStore.mark_done()                             │
│  Sets done key (24h TTL), deletes processing key                     │
│  Pub/Sub message ACK'd                                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Module Reference

### 3.1 config.py

**File**: `app/bridge/google_chat/config.py` (99 lines)

**Purpose**: Centralizes all configuration for the bridge using Pydantic Settings. Loads values from `.env` files, provides computed properties, and validates required fields at startup.

#### Class: `GoogleChatBridgeSettings`

Inherits from `pydantic_settings.BaseSettings`. Loads environment variables with case-insensitive matching from `.env` or `app/.env`.

| Field | Env Var | Type | Default | Description |
|-------|---------|------|---------|-------------|
| `google_cloud_project` | `GOOGLE_CLOUD_PROJECT` | `str` | `""` | GCP project ID |
| `google_chat_subscription` | `GOOGLE_CHAT_SUBSCRIPTION` | `str` | `""` | Full Pub/Sub subscription path (`projects/.../subscriptions/...`) |
| `google_application_credentials` | `GOOGLE_APPLICATION_CREDENTIALS` | `str` | `./secrets/chat-bot-secret.json` | Path to service account JSON |
| `google_chat_scopes_raw` | `GOOGLE_CHAT_SCOPES` | `str` | Space-separated OAuth scopes | Raw scopes string, parsed by `google_chat_scopes` property |
| `agent_internal_url` | `AGENT_INTERNAL_URL` | `str` | `http://localhost:8002/chat` | Agent Bot endpoint URL |
| `google_chat_send_thinking_message` | `GOOGLE_CHAT_SEND_THINKING_MESSAGE` | `bool` | `True` | Whether to send "thinking" placeholder |
| `google_chat_thinking_text` | `GOOGLE_CHAT_THINKING_TEXT` | `str` | `"Um momento..."` | Text of the thinking placeholder |
| `redis_url` | `REDIS_URL` | `str` | `redis://localhost:6379/0` | Redis URL for deduplication |
| `google_chat_dedupe_ttl_seconds` | `GOOGLE_CHAT_DEDUPE_TTL_SECONDS` | `int` | `86400` (24h) | TTL for "done" dedup key |

#### Computed Properties

- **`google_chat_scopes`** → `list[str]`: Splits `google_chat_scopes_raw` by whitespace, strips each scope. Default yields `["https://www.googleapis.com/auth/chat.bot", "https://www.googleapis.com/auth/chat.messages.readonly"]`.
- **`service_account_path`** → `Path`: Resolves and expands the credentials file path.

#### Method: `validate_google_chat_config()`

Checks all required fields and verifies the service account file exists on disk. Raises `RuntimeError` with a concatenated list of all validation errors if any fail. This is called at worker startup to fail fast on misconfiguration.

#### Singleton: `get_google_chat_bridge_settings()`

Decorated with `@lru_cache(maxsize=1)`. Returns a single `GoogleChatBridgeSettings` instance for the process lifetime.

---

### 3.2 models.py

**File**: `app/bridge/google_chat/models.py` (116 lines)

**Purpose**: Defines the core data structures that represent parsed Google Chat events. All dataclasses use `slots=True` for memory efficiency.

#### Class: `GoogleChatUser`

Represents the sender of a message.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Resource name (e.g., `users/123`) |
| `display_name` | `str` | Human-readable name |
| `email` | `str` | User's email address |
| `type` | `str` | `"HUMAN"` or `"BOT"` |
| `domain_id` | `str` | Google Workspace domain ID |

#### Class: `GoogleChatAttachment`

Represents a file attachment in a message.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Attachment resource name |
| `content_name` | `str` | Original filename |
| `content_type` | `str` | MIME type (e.g., `image/png`) |
| `resource_name` | `str` | API resource name for download |
| `source` | `str` | Origin (`"UPLOADED_CONTENT"`, etc.) |
| `thumbnail_uri` | `str` | URI to thumbnail preview |
| `download_uri` | `str` | Direct download URI |

**Properties**:

- **`is_uploaded_content`** → `bool`: `True` if `source == "UPLOADED_CONTENT"` (case-insensitive). Only uploaded content can be downloaded via the Chat API.
- **`is_image`** → `bool`: `True` if `content_type` starts with `"image/"`.
- **`can_download_with_chat_api`** → `bool`: `True` if both `is_uploaded_content` and `resource_name` is non-empty. This is the gate for whether the media downloader should attempt download.

#### Class: `GoogleChatIncomingMessage`

The primary parsed event object. Contains all information about an incoming Google Chat event.

**Core Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `pubsub_message_id` | `str` | Pub/Sub message ID for deduplication |
| `event_type` | `str` | `"MESSAGE"`, `"SPACE_EVENT"`, `"UNKNOWN"` |
| `space_name` | `str` | Space resource name (e.g., `spaces/AAAA...`) |
| `space_type` | `str` | `"ROOM"`, `"DM"`, etc. |
| `space_threading_state` | `str` | Threading state of the space |
| `message_name` | `str` | Message resource name (used for replies and dedup) |
| `message_text` | `str` | Raw message text from Google |
| `argument_text` | `str` | Text after bot command mention |
| `formatted_text` | `str` | Rich-text formatted version |
| `thread_name` | `str` | Thread resource name (for threaded replies) |
| `create_time` | `str` | Message creation timestamp |
| `event_time` | `str` | Event timestamp |
| `user` | `GoogleChatUser` | Sender information |
| `attachments` | `list[GoogleChatAttachment]` | All attachments |
| `user_locale` | `str` | User's locale (e.g., `"pt-BR"`) |
| `time_zone_id` | `str` | User's timezone ID |
| `time_zone_offset` | `int \| None` | Timezone offset from UTC in seconds |
| `raw_event` | `dict` | Complete raw event for debugging |

**Key Properties**:

- **`is_from_bot`** → `bool`: `True` if sender type is `"BOT"`. Used to filter out the bot's own messages.
- **`is_from_human`** → `bool`: `True` if sender type is `"HUMAN"`.
- **`clean_text`** → `str`: Returns the best available text in priority order: `argument_text` → `message_text` → `formatted_text`. Strips whitespace.
- **`has_text`** → `bool`: `True` if `clean_text` is non-empty.
- **`has_attachments`** → `bool`: `True` if attachment list is non-empty.
- **`has_image_attachments`** → `bool`: `True` if any attachment `is_image`.
- **`can_process`** → `bool`: The central decision gate. Returns `True` only if ALL of:
  1. `event_type == "MESSAGE"`
  2. Has text OR has image attachments
  3. `space_name` is non-empty
  4. `message_name` is non-empty
  5. Not from a bot (`not is_from_bot`)

  This prevents processing bot echoes, empty events, space-only events, and events missing required identifiers.

- **`to_log_dict()`** → `dict`: Structured dictionary for logging, includes counts of attachments and images.

---

### 3.3 parser.py

**File**: `app/bridge/google_chat/parser.py` (141 lines)

**Purpose**: Pure-function module that transforms raw Pub/Sub JSON payloads into `GoogleChatIncomingMessage` objects. No side effects, no I/O.

#### Main Function: `parse_google_chat_event(data)`

Takes the raw dict from Pub/Sub and drills into the nested structure:

```
data
├── payload (or data itself)
│   ├── chat
│   │   ├── messagePayload
│   │   │   ├── message
│   │   │   │   ├── name
│   │   │   │   ├── text / argumentText / formattedText
│   │   │   │   ├── sender
│   │   │   │   ├── thread
│   │   │   │   └── attachment[]
│   │   │   └── space
│   │   ├── user (fallback sender)
│   │   └── eventTime
│   └── commonEventObject
│       ├── timeZone
│       └── userLocale
```

**Key logic**:

1. **`_extract_event(data)`**: Finds the event dict. Checks if `data["payload"]` contains `"chat"` or `"commonEventObject"` keys; if not, checks `data` itself. Returns empty dict if neither found.

2. **`_detect_event_type(event, message_payload)`**: Determines event type by checking, in order:
   - Explicit `type`/`eventType` field on the event or messagePayload
   - Presence of `message` key → `"MESSAGE"`
   - Presence of `space` key → `"SPACE_EVENT"`
   - Fallback → `"UNKNOWN"`

3. **`_parse_attachments(message)`**: Handles both `"attachment"` and `"attachments"` keys (Google Chat API inconsistency). For each raw attachment, extracts nested `attachmentDataRef.resourceName`.

4. **Sender fallback**: Tries `message.sender` first, falls back to `chat.user` (different event formats).

5. **Timezone**: Extracts from `commonEventObject.timeZone.id` and `.offset`.

#### Helper Functions

- **`_as_dict(value)`**: Safe cast to `dict`, returns `{}` if not a dict. Prevents `AttributeError` on `None` or unexpected types.
- **`_parse_optional_int(value)`**: Safe int conversion, returns `None` on failure.

---

### 3.4 pubsub_subscriber.py

**File**: `app/bridge/google_chat/pubsub_subscriber.py` (153 lines)

**Purpose**: Manages the Google Cloud Pub/Sub connection and provides message decoding. Can run standalone for testing.

#### Class: `GoogleChatPubSubSubscriber`

**Constructor**: Loads settings, creates `service_account.Credentials` from the service account file, initializes `pubsub_v1.SubscriberClient`.

**Method: `listen_once(timeout_seconds, ack)`**

Used for testing. Subscribes to the Pub/Sub subscription, waits for a single message, then cancels the subscription.

- Uses a `threading.Event` to signal when a message arrives
- The callback decodes the message, optionally ACKs or NACKs it
- Returns the decoded payload dict, or `None` on timeout
- Always closes the subscriber client in the `finally` block

**Static Method: `decode_message(message)`**

Transforms a raw `pubsub_v1.subscriber.message.Message` into a structured dict:

```python
{
    "pubsubMessageId": message.message_id,
    "publishTime": str(message.publish_time),
    "attributes": dict(message.attributes),
    "payload": json.loads(message.data),  # or {"rawText": ...} on JSONDecodeError
    "rawDataBase64": base64.b64encode(message.data)
}
```

The JSON decode is wrapped in try/except — if the Pub/Sub message isn't valid JSON, it stores the raw text under `"rawText"`.

#### Standalone Mode

Running `python -m app.bridge.google_chat.pubsub_subscriber` starts a CLI with `--timeout` and `--ack` flags for manual testing of the Pub/Sub connection.

---

### 3.5 media_downloader.py

**File**: `app/bridge/google_chat/media_downloader.py` (184 lines)

**Purpose**: Downloads image attachments from Google Chat using the Chat API's media download endpoint, then encodes them as base64 for the Agent Bot.

#### Constants

- **`DEFAULT_ALLOWED_IMAGE_TYPES`**: `{"image/png", "image/jpeg", "image/jpg", "image/webp"}`

#### Dataclass: `DownloadedGoogleChatImage`

| Field | Type | Description |
|-------|------|-------------|
| `filename` | `str` | Original filename from attachment |
| `content_type` | `str` | MIME type |
| `size_bytes` | `int` | Downloaded size in bytes |
| `base64_data` | `str` | Base64-encoded image bytes |
| `attachment_name` | `str` | Attachment resource name |
| `resource_name` | `str` | API resource name |

#### Class: `GoogleChatMediaDownloader`

**Constructor Parameters**:

| Param | Default | Description |
|-------|---------|-------------|
| `settings` | `None` (loads singleton) | Bridge settings |
| `max_images` | `4` | Maximum images per message |
| `max_image_bytes` | `10 * 1024 * 1024` (10 MB) | Max bytes per image |
| `allowed_image_types` | `DEFAULT_ALLOWED_IMAGE_TYPES` | Allowed MIME types |

**Lazy Service**: The Google Chat API service is created on first access via the `service` property, using the same service account credentials and scopes as other components.

**Method: `download_images_from_event(event)`**

Iterates over `event.attachments`:
1. Checks if `max_images` limit is reached → stops
2. Calls `_should_download_attachment()` to filter
3. Calls `download_image_attachment()` for each valid attachment
4. Returns `list[DownloadedGoogleChatImage]`

**Method: `download_image_attachment(attachment)`**

Downloads a single attachment:
1. Calls `service.media().download_media(resourceName=attachment.resource_name)`
2. Uses `MediaIoBaseDownload` for chunked download into a `BytesIO` buffer
3. Checks size after each chunk — raises `RuntimeError` if exceeding `max_image_bytes`
4. Base64-encodes the downloaded bytes
5. Returns a `DownloadedGoogleChatImage` dataclass

**Method: `_should_download_attachment(attachment)`**

Returns `True` only if:
1. `attachment.can_download_with_chat_api` is `True` (is uploaded content + has resource name)
2. `attachment.content_type` is in `allowed_image_types`

---

### 3.6 chat_client.py

**File**: `app/bridge/google_chat/chat_client.py` (216 lines)

**Purpose**: Wraps the Google Chat API for sending and updating messages in Google Chat spaces.

#### Constants

- **`SAFE_CHAT_MESSAGE_BYTES`**: `30000` (30 KB) — Maximum UTF-8 byte size for a Chat message. Google Chat rejects messages exceeding this limit.

#### Class: `GoogleChatClient`

**Lazy Service**: Same pattern as `GoogleChatMediaDownloader` — creates the `chat v1` API service on first access.

**Method: `send_text(space_name, text, thread_name)`**

Sends a new message to a Google Chat space.

- **Validation**: `space_name` must be non-empty and start with `"spaces/"`. Raises `ValueError` otherwise.
- **Text normalization**: Calls `_normalize_text()` which strips whitespace, replaces empty text with `"Mensagem vazia."`, and truncates to `SAFE_CHAT_MESSAGE_BYTES`.
- **Thread support**: If `thread_name` is provided, sets `body["thread"]["name"]` and uses `messageReplyOption: "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"` to reply in-thread or create a new thread.
- **API call**: `service.spaces().messages().create(parent=space_name, body=body).execute()`
- **Error handling**: Catches `HttpError`, extracts status and content, wraps in `RuntimeError`.

**Method: `update_text(message_name, text)`**

Patches an existing message (used to replace the "thinking" placeholder with the final answer).

- **Validation**: `message_name` must start with `"spaces/"`.
- **API call**: `service.spaces().messages().patch(name=message_name, updateMask="text", body=body).execute()`
- Only the `text` field is updated via `updateMask`.

**Method: `send_thinking(space_name, thread_name)`**

Convenience wrapper that calls `send_text()` with `settings.google_chat_thinking_text` (default: `"Um momento..."`).

**Static Method: `truncate_utf8(text, max_bytes)`**

Ensures the message fits within Google Chat's byte limit:
1. Encodes text to UTF-8
2. If within limit, returns as-is
3. Otherwise, reserves space for a `"\n\n[Mensagem truncada por limite do Google Chat.]"` suffix
4. Truncates the encoded bytes, then walks backward to avoid splitting a multi-byte UTF-8 character
5. Falls back to `"[Mensagem truncada.]"` if the suffix alone exceeds the limit

---

### 3.7 agent_adapter.py

**File**: `app/bridge/google_chat/agent_adapter.py` (183 lines)

**Purpose**: HTTP client that calls the Agent Bot's internal `/chat` endpoint and extracts the answer from the response.

#### Class: `AgentAdapter`

**Constructor**:

| Param | Default | Description |
|-------|---------|-------------|
| `settings` | `None` (loads singleton) | Bridge settings |
| `timeout_seconds` | `180.0` | HTTP timeout (3 minutes, agent can be slow) |

**Method: `ask(event, images)`**

The core method that sends a user's message to the agent and returns the answer string.

1. **Pre-check**: Raises `ValueError` if `event.can_process` is `False`.
2. **Payload building**: Calls `_build_agent_payload()`.
3. **HTTP POST**: Sends to `settings.agent_internal_url` with JSON body. Uses `httpx.Client` (synchronous).
4. **Error handling**:
   - `HTTPStatusError` → wraps status + response body in `RuntimeError`
   - `RequestError` → wraps connection failure in `RuntimeError`
5. **Answer extraction**: Calls `_extract_answer()` on the response.
6. **Fallback**: If answer is empty, returns `"Não consegui gerar uma resposta para essa mensagem."`.

**Method: `_build_agent_payload(event, images)`**

Constructs the JSON payload matching the Agent Bot's `ChatRequest` schema:

```json
{
    "message": "user's text or OCR instruction",
    "user_id": "google-chat-user",
    "images": [
        {
            "image_base64": "...",
            "mime_type": "image/png",
            "file_name": "photo.png",
            "image_index": 0
        }
    ]
}
```

- **`user_id`**: Falls back through `user.name` → `user.email` → `"google-chat-user"`.
- **OCR instruction**: If images are present but text is empty, injects: `"Faça OCR da imagem enviada e responda com base no texto extraído. Se a imagem contiver apenas uma tag, retorne a tag identificada."`
- **Images**: Only included if the list is non-empty.

**Static Method: `_extract_answer(response)`**

Handles multiple response formats:
1. If `Content-Type` is not JSON → returns raw `response.text`
2. If JSON parsing fails → returns raw text
3. Delegates to `_extract_text_from_json()`

**Static Method: `_extract_text_from_json(data)`**

Resilient text extraction that tries these keys in order:
`response`, `answer`, `message`, `content`, `text`, `output`, `result`, `reply`, `assistant_message`, `final_answer`

If none match, recursively checks `data["data"]` (handles nested response wrappers like `{"data": {"output": "..."}}`).

---

### 3.8 dedupe_store.py

**File**: `app/bridge/google_chat/dedupe_store.py` (210 lines)

**Purpose**: Prevents the same Google Chat message from being processed multiple times, which would cause duplicate bot responses.

#### Why Deduplication is Needed

Google Chat Pub/Sub can deliver the same message multiple times (at-least-once delivery). Without deduplication, a user would see the bot respond twice (or more) to the same message.

#### Two-Key Strategy

The store uses **two Redis keys** per message:

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `google_chat:dedupe:processing:{message_name}` | 900s (15 min) | Set with `NX` while processing. Prevents concurrent processing of the same message. |
| `google_chat:dedupe:done:{message_name}` | 86400s (24h) | Set after successful processing. Prevents reprocessing of already-handled messages. |

**State transitions**:

```
New message
  │
  ├─ done key exists? → "duplicate_done" (ACK, skip)
  │
  ├─ processing key exists? → "duplicate_processing" (ACK, skip)
  │
  └─ Neither exists → SET processing key (NX) → "started"
        │
        ├─ On success: mark_done() → SET done key, DELETE processing key
        │
        └─ On error: release_processing() → DELETE processing key
```

#### Type: `DedupeStatus`

```python
DedupeStatus = Literal["started", "duplicate_done", "duplicate_processing"]
```

#### Class: `DedupeStore`

**Constructor**:

| Param | Default | Description |
|-------|---------|-------------|
| `settings` | `None` (loads singleton) | Bridge settings |
| `processing_ttl_seconds` | `900` (15 min) | TTL for processing key |

**Redis Initialization**: Connects to Redis using `settings.redis_url`. If connection fails, falls back to in-memory dict with TTL simulation.

**Method: `try_start(event)`**

1. Derives `message_key` from `event.message_name` (or `event.pubsub_message_id` as fallback).
2. Checks if `done` key exists → returns `"duplicate_done"`
3. Attempts `SET processing_key` with `NX` and `EX=900` → if set, returns `"started"`, else `"duplicate_processing"`

**Method: `mark_done(event)`**

1. Sets `done` key with `EX=settings.google_chat_dedupe_ttl_seconds` (default 24h)
2. Deletes `processing` key

**Method: `release_processing(event)`**

Deletes the `processing` key without setting `done`. Used in test mode or when an error occurs and we want to allow retry.

**In-Memory Fallback**:

When Redis is unavailable, the store uses a plain `dict[str, MemoryEntry]` with timestamp-based expiry. The `_cleanup_memory()` method purges expired entries on each operation. This is suitable for single-process testing but not for production (no cross-process coordination).

---

### 3.9 worker.py

**File**: `app/bridge/google_chat/worker.py` (335 lines)

**Purpose**: The main orchestrator that ties all components together. This is the entry point for the bridge process.

#### Constants

- **`FAILURE_MESSAGE`**: `"Não consegui processar essa mensagem. A solicitação foi encerrada para evitar repetição automática."` — Sent to the user when processing fails.

#### Class: `GoogleChatBridgeWorker`

**Constructor**:

| Param | Default | Description |
|-------|---------|-------------|
| `settings` | `None` (loads singleton) | Bridge settings |
| `send_to_chat` | `False` | If `True`, sends responses to Google Chat. If `False`, only logs (test mode). |

Initializes all sub-components:
- `pubsub_v1.SubscriberClient` with service account credentials
- `AgentAdapter`
- `GoogleChatClient`
- `DedupeStore`
- `GoogleChatMediaDownloader`

**Method: `run_once(timeout_seconds)`**

For single-message testing. Subscribes to Pub/Sub, processes one message, then shuts down. Uses `threading.Event` to wait for the callback to complete.

**Method: `run_forever()`**

For production. Subscribes to Pub/Sub and processes messages indefinitely until `KeyboardInterrupt`. Gracefully cancels the streaming future on shutdown.

**Method: `process_pubsub_message(message)`**

The core pipeline, called for every incoming Pub/Sub message:

```
1. decode_message(message) → payload
2. parse_google_chat_event(payload) → event
3. Log event details
4. can_process? → if no: ACK (prod) or NACK (test), return
5. try_start(event) → dedupe_status
6. If duplicate: ACK (prod) or NACK (test), return
7. Send "thinking" message (if send_to_chat + enabled)
8. download_images_from_event(event) → downloaded_images
9. agent_adapter.ask(event, images) → answer
10. Log answer
11. If send_to_chat:
    a. If thinking_message_name exists → update_text() with answer
    b. Else → send_text() as new message
    c. mark_done(event)
    d. ACK message
12. Else (test mode):
    a. release_processing(event)
    b. NACK message
```

**Method: `_finish_after_error(...)`**

Called when an exception occurs during processing. Handles cleanup:

1. **Dedupe cleanup**: If dedup was started, marks as done (so the message isn't retried indefinitely).
2. **Chat feedback** (if `send_to_chat`):
   - If a thinking message was sent → updates it with `FAILURE_MESSAGE`
   - ACKs the Pub/Sub message (critical: prevents infinite retry loops)
3. **Test mode**: Releases processing dedup, NACKs the message (allows retry).

#### CLI: `main()`

Entry point when running `python -m app.bridge.google_chat.worker`.

| Flag | Description |
|------|-------------|
| `--once` | Process a single message and exit |
| `--timeout` | Timeout in seconds for `--once` mode (default: 120) |
| `--send` | Enable sending responses to Google Chat (default: log only) |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |

---

## 4. Test Scripts

### 4.1 test_download_image.py

**File**: `app/bridge/google_chat/test_download_image.py` (104 lines)

**Purpose**: Manual test script that listens for a Pub/Sub message, parses it, downloads all image attachments, and saves them to disk.

**Flow**:
1. Parses CLI args (`--timeout`, `--output-dir`)
2. Creates output directory (default: `/tmp/google_chat_images/`)
3. Subscribes to Pub/Sub and waits for one message
4. Parses the event, prints attachment metadata
5. Downloads images via `GoogleChatMediaDownloader`
6. Saves each image to disk with proper file extension
7. Prints download details (filename, content type, size, base64 length, save path)

**Helper**: `_suffix_from_content_type()` maps MIME types to file extensions (`.png`, `.jpg`, `.webp`, `.bin`).

### 4.2 test_send_message.py

**File**: `app/bridge/google_chat/test_send_message.py` (70 lines)

**Purpose**: Manual test script that sends a text message to a specified Google Chat space.

**Flow**:
1. Parses CLI args (`--space`, `--thread`, `--text`)
2. Validates `--space` is provided (falls back to `GOOGLE_CHAT_TEST_SPACE` env var)
3. Loads settings, validates config
4. Sends message via `GoogleChatClient.send_text()`
5. Prints result (message name, space, thread, text)

---

## 5. Docker Deployment

The bridge runs as a separate container alongside the Agent Bot in the same Docker Compose network.

### Service Definition

```yaml
agent_bot_chat_bridge:
  build:
    context: .
    dockerfile: Dockerfile
  image: agent_bot:0.2.0
  container_name: agent_bot_chat_bridge
  restart: always
  command: python -m app.bridge.google_chat.worker --send
  env_file:
    - ./app/.env
  environment:
    - AGENT_INTERNAL_URL=http://agent_bot:8002/chat
    - GOOGLE_APPLICATION_CREDENTIALS=./secrets/chat_secret.json
    - PYTHONUNBUFFERED=1
  volumes:
    - ./secrets:/app/secrets:ro
  depends_on:
    - agent_bot
```

### Key Details

- **Same image**: Uses the same `agent_bot:0.2.0` image as the main API, just a different `command`.
- **Internal URL**: Communicates with the Agent Bot via Docker's internal network (`http://agent_bot:8002/chat`), not localhost.
- **Secrets**: The service account JSON is mounted as a read-only volume at `/app/secrets/`.
- **`PYTHONUNBUFFERED=1`**: Ensures Python logs are immediately flushed to Docker's log collector.
- **`--send` flag**: Enables actual message sending to Google Chat (without it, the bridge only logs).
- **`restart: always`**: Container restarts automatically on failure or Docker daemon restart.
- **`depends_on`**: Starts after the `agent_bot` container is healthy.

### Network Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                           │
│                                                             │
│  ┌──────────────────┐         ┌──────────────────────────┐ │
│  │   agent_bot       │         │  agent_bot_chat_bridge    │ │
│  │   :8002           │◄────────│  (worker --send)          │ │
│  │   FastAPI /chat   │  HTTP   │  Pub/Sub subscriber       │ │
│  └──────────────────┘         └────────────┬─────────────┘ │
│                                              │               │
│                                              │ Pub/Sub       │
│                                              │ (external)    │
└──────────────────────────────────────────────┼───────────────┘
                                               │
                                               ▼
                                   ┌──────────────────────┐
                                   │  Google Cloud Pub/Sub │
                                   │  (external service)   │
                                   └──────────────────────┘
```

---

## 6. Environment Variables Reference

All variables are set in `app/.env` (or overridden in `docker-compose.yaml`).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Yes | — | Google Cloud project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes | `./secrets/chat-bot-secret.json` | Path to service account JSON file |
| `GOOGLE_CHAT_SUBSCRIPTION` | Yes | — | Full Pub/Sub subscription resource name (`projects/{project}/subscriptions/{sub}`) |
| `GOOGLE_CHAT_SCOPES` | No | `https://www.googleapis.com/auth/chat.bot https://www.googleapis.com/auth/chat.messages.readonly` | Space-separated OAuth scopes |
| `AGENT_INTERNAL_URL` | No | `http://localhost:8002/chat` | Agent Bot chat endpoint URL |
| `GOOGLE_CHAT_SEND_THINKING_MESSAGE` | No | `true` | Send "Um momento..." placeholder while processing |
| `GOOGLE_CHAT_THINKING_TEXT` | No | `Um momento...` | Text of the thinking placeholder |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis URL for deduplication store |
| `GOOGLE_CHAT_DEDUPE_TTL_SECONDS` | No | `86400` (24h) | TTL for "done" deduplication key |

### Required Google Cloud Setup

1. **Service Account** with these roles:
   - `roles/chat.bot` — Send messages, update messages
   - `roles/pubsub.subscriber` — Pull messages from Pub/Sub subscription

2. **Pub/Sub Subscription** linked to a Google Chat space's Pub/Sub topic:
   - Topic is auto-created by Google Chat when a space is configured for events
   - Subscription must be created manually (pull or push)

3. **Google Chat API** must be enabled in the GCP project

---

## 7. Error Handling & Edge Cases

### ACK vs NACK Strategy

| Scenario | Production (`--send`) | Test Mode (no `--send`) |
|----------|----------------------|------------------------|
| Event not processable | `ACK` | `NACK` |
| Duplicate message | `ACK` | `NACK` |
| Processing succeeded | `ACK` | `NACK` |
| Processing failed | `ACK` (via `_finish_after_error`) | `NACK` |

**Why ACK on failure in production?**: Google Pub/Sub retries NACK'd messages. If processing fails (e.g., agent is down), NACKing would cause infinite retries and duplicate "thinking" messages. ACKing stops the retry loop.

### Error Recovery Flow

```
Exception in process_pubsub_message()
  │
  ├─ dedupe_started?
  │   └─ Yes → mark_done() (prevent future retries)
  │
  ├─ send_to_chat?
  │   ├─ Yes → update thinking message with FAILURE_MESSAGE
  │   │       → ACK the Pub/Sub message
  │   └─ No → release_processing() (allow retry in test)
  │           → NACK the Pub/Sub message
  │
  └─ Log full traceback
```

### Edge Cases Handled

1. **Bot messages**: Filtered out by `is_from_bot` check in `can_process`. Prevents the bot from responding to its own messages or other bots.

2. **Empty messages**: `can_process` requires either text or image attachments. Space-only events (user joins/leaves) are ignored.

3. **Missing identifiers**: If `space_name` or `message_name` is empty, `can_process` returns `False`.

4. **Google Chat byte limit**: Messages are truncated to 30KB UTF-8 with a warning suffix, preventing API rejection.

5. **Image download failures**: If a single image fails to download, the exception propagates to `process_pubsub_message` and triggers `_finish_after_error`. The thinking message is updated with the failure message.

6. **Agent timeout**: The `AgentAdapter` has a 180-second timeout. Longer-running queries may time out, triggering error handling.

7. **Redis unavailable**: `DedupeStore` falls back to in-memory dict. Suitable for single-process testing but not production (no cross-process dedup).

8. **Concurrent processing**: The `processing` key with `NX` prevents two instances from processing the same message simultaneously. If a second Pub/Sub delivery arrives while the first is still processing, it sees the `processing` key and skips.

9. **Stale processing keys**: The `processing` key has a 15-minute TTL. If a worker crashes mid-processing, the key expires and the message can be retried.

10. **Message format variations**: The parser handles multiple Google Chat event structures (with/without `payload` wrapper, `attachment` vs `attachments` key, `sender` vs `user` location).

---

## Quick Reference

### Run the Worker

```bash
# Production (send responses to Google Chat)
python -m app.bridge.google_chat.worker --send

# Test mode (log only, NACK all messages)
python -m app.bridge.google_chat.worker

# Single message mode (useful for debugging)
python -m app.bridge.google_chat.worker --once --timeout 60

# Debug logging
python -m app.bridge.google_chat.worker --send --log-level DEBUG
```

### Test Manually

```bash
# Send a test message to a space
python -m app.bridge.google_chat.test_send_message --space "spaces/AAAA..." --text "Hello from bridge"

# Listen for one message and download images
python -m app.bridge.google_chat.test_download_image --timeout 120 --output-dir /tmp/images
```

### Docker

```bash
# Start the bridge container
docker compose up -d agent_bot_chat_bridge

# View logs
docker compose logs -f agent_bot_chat_bridge

# Restart
docker compose restart agent_bot_chat_bridge
```
