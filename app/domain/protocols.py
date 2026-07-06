"""Repository and service Protocols — domain-side abstractions.

These define WHAT the domain needs, not HOW it's implemented.
Concrete implementations live in app/clients/ and app/services/.

For Etapa 1, we add the abstractions; Etapa 2 will annotate existing
implementations as conforming to these Protocols.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Protocol, runtime_checkable

from app.domain.enums import TemporalDataMethod
from app.domain.value_objects import (
    CalculationBasis,
    EngineeringUnit,
    PiWebId,
    SummaryType,
    TimeUnit,
    TimeWindow,
)

if TYPE_CHECKING:
    from app.schemas.chat import ChatImage


# ---------------------------------------------------------------------------
# Aggregates (forward declarations — minimal Protocol stubs)
# ---------------------------------------------------------------------------


class PiPointLike(Protocol):
    """Minimal interface of a PI Point for Protocol typing."""

    web_id: str
    name: str
    descriptor: str
    point_type: str
    engineering_units: str
    digital_set: str | None


class PiTagValueLike(Protocol):
    """Minimal interface of a current PI tag value."""

    value: float | int | str | None
    timestamp: str
    good: bool
    questionable: bool


class TagSeriesLike(Protocol):
    """Minimal interface of a temporal series."""

    points: list[tuple[str, float]]
    engineering_unit: str | None


class ConversationTurnLike(Protocol):
    """Minimal interface of a memory turn."""

    role: str
    content: str
    created_at: str
    metadata: dict


class KnowledgeChunkLike(Protocol):
    """Minimal interface of a knowledge chunk."""

    chunk_number: int
    title: str
    content: str
    score: float


class OcrExtractionLike(Protocol):
    """Minimal interface of an OCR result."""

    image_index: int
    text: str
    tags: list[str]


# ---------------------------------------------------------------------------
# Protocols (interfaces)
# ---------------------------------------------------------------------------


@runtime_checkable
class PIPointRepository(Protocol):
    """Repository for PI Points and their temporal data."""

    async def get_point_by_tag(self, tag: str) -> PiPointLike: ...

    async def get_current_value(self, web_id: PiWebId) -> PiTagValueLike: ...

    async def get_recorded_series(
        self, web_id: PiWebId, window: TimeWindow, max_count: int
    ) -> TagSeriesLike: ...

    async def get_interpolated_series(
        self, web_id: PiWebId, window: TimeWindow, interval: str
    ) -> TagSeriesLike: ...

    async def get_summary_series(
        self,
        web_id: PiWebId,
        window: TimeWindow,
        summary_type: SummaryType,
        summary_duration: str,
        calculation_basis: CalculationBasis,
    ) -> TagSeriesLike: ...


@runtime_checkable
class KnowledgeRepository(Protocol):
    """Repository for RAG knowledge chunks."""

    def get_fixed_chunk(self) -> str: ...

    def retrieve_relevant(self, query: str, top_k: int) -> list[KnowledgeChunkLike]: ...

    def build_context(
        self, query: str, top_k: int, include_fixed: bool
    ) -> str: ...


@runtime_checkable
class ConversationMemory(Protocol):
    """Repository for conversation memory turns."""

    async def load_turns(
        self, conversation_id: str, max_turns: int | None = None
    ) -> list[ConversationTurnLike]: ...

    async def append_turns(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        metadata: dict | None = None,
    ) -> None: ...

    def format_for_prompt(self, turns: list[ConversationTurnLike]) -> str: ...


@runtime_checkable
class OcrService(Protocol):
    """Service for extracting text and tags from images."""

    async def extract(self, image: ChatImage) -> OcrExtractionLike: ...

    async def extract_batch(
        self, images: list[ChatImage]
    ) -> list[OcrExtractionLike]: ...


@runtime_checkable
class MathToolClient(Protocol):
    """Client for the Math Tool service."""

    async def calculate(self, expression: str) -> float: ...

    async def stats(self, values: list[float], operations: list[str]) -> dict: ...

    async def calculus(
        self, operation: str, time_unit: TimeUnit, points: list[tuple[str, float]]
    ) -> float: ...


@runtime_checkable
class PimsOpsRepository(Protocol):
    """Repository for PIMS operational status (via Loki)."""

    async def get_status_report(
        self, lookback_minutes: int | None = None
    ) -> dict: ...


@runtime_checkable
class ConversationMemorySaver(Protocol):
    """Protocol for persisting a conversation turn from outbox event payload."""

    async def save(self, payload: Mapping[str, Any]) -> None: ...
