"""Shared fixtures for application layer tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.protocols import (
    ConversationMemory,
    KnowledgeRepository,
    OcrService,
    PIPointRepository,
    PimsOpsRepository,
)


# ---------------------------------------------------------------------------
# Fake domain objects (satisfy Protocol stubs without real infrastructure)
# ---------------------------------------------------------------------------


@dataclass
class FakePiPoint:
    web_id: str = "fake-web-id-123"
    name: str = "LFI_RB3_VAZ_GN_TOTAL"
    descriptor: str = "Vazao GN Total"
    point_type: str = "Float"
    engineering_units: str = "Nm3/h"
    digital_set: str | None = None


@dataclass
class FakePiTagValue:
    value: float | int | str | None = 1523.4
    timestamp: str = "2026-06-23T10:00:00-03:00"
    good: bool = True
    questionable: bool = False


@dataclass
class FakeTagSeries:
    points: list[tuple[str, float]] = field(default_factory=list)
    engineering_unit: str | None = "Nm3/h"


@dataclass
class FakeKnowledgeChunk:
    chunk_number: int = 1
    title: str = "CHUNK 01 - Fixo"
    content: str = "Conteudo do chunk"
    score: float = 0.95


@dataclass
class FakeOcrExtraction:
    image_index: int = 0
    text: str = "Tag: LFI_RB3_VAZ_GN_TOTAL"
    tags: list[str] = field(default_factory=lambda: ["LFI_RB3_VAZ_GN_TOTAL"])


@dataclass
class FakeConversationTurn:
    role: str = "user"
    content: str = "qual o valor"
    created_at: str = "2026-06-23T10:00:00-03:00"
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_pi_point() -> FakePiPoint:
    return FakePiPoint()


@pytest.fixture
def fake_pi_tag_value() -> FakePiTagValue:
    return FakePiTagValue()


@pytest.fixture
def fake_tag_series() -> FakeTagSeries:
    return FakeTagSeries(points=[("2026-06-23T00:00:00", 1500.0)])


@pytest.fixture
def fake_knowledge_chunk() -> FakeKnowledgeChunk:
    return FakeKnowledgeChunk()


@pytest.fixture
def fake_ocr_extraction() -> FakeOcrExtraction:
    return FakeOcrExtraction()


@pytest.fixture
def fake_conversation_turn() -> FakeConversationTurn:
    return FakeConversationTurn()


@pytest.fixture
def mock_ocr_service(fake_ocr_extraction: FakeOcrExtraction) -> MagicMock:
    service = MagicMock(spec=OcrService)
    service.extract_batch = AsyncMock(return_value=[fake_ocr_extraction])
    service.extract = AsyncMock(return_value=fake_ocr_extraction)
    return service


@pytest.fixture
def mock_knowledge_repo(fake_knowledge_chunk: FakeKnowledgeChunk) -> MagicMock:
    repo = MagicMock(spec=KnowledgeRepository)
    repo.build_context = MagicMock(return_value="FAKE CONTEXT")
    repo.retrieve_relevant = MagicMock(return_value=[fake_knowledge_chunk])
    repo.get_fixed_chunk = MagicMock(return_value="FIXED CHUNK 01")
    return repo


@pytest.fixture
def mock_conversation_memory(fake_conversation_turn: FakeConversationTurn) -> MagicMock:
    memory = MagicMock(spec=ConversationMemory)
    memory.load_turns = AsyncMock(return_value=[fake_conversation_turn])
    memory.append_turns = AsyncMock()
    memory.format_for_prompt = MagicMock(return_value="> user: qual o valor")
    return memory


@pytest.fixture
def mock_pi_repo(
    fake_pi_point: FakePiPoint, fake_pi_tag_value: FakePiTagValue
) -> MagicMock:
    repo = MagicMock(spec=PIPointRepository)
    repo.get_point_by_tag = AsyncMock(return_value=fake_pi_point)
    repo.get_current_value = AsyncMock(return_value=fake_pi_tag_value)
    repo.get_recorded_series = AsyncMock(
        return_value=FakeTagSeries(points=[("2026-06-23", 1500.0)])
    )
    repo.get_interpolated_series = AsyncMock(
        return_value=FakeTagSeries(points=[("2026-06-23", 1500.0)])
    )
    repo.get_summary_series = AsyncMock(
        return_value=FakeTagSeries(points=[("2026-06-23", 1500.0)])
    )
    return repo


@pytest.fixture
def mock_pims_ops_repo() -> MagicMock:
    repo = MagicMock(spec=PimsOpsRepository)
    repo.get_status_report = AsyncMock(
        return_value={"total_logs": 100, "errors": 2, "warnings": 5}
    )
    return repo


@pytest.fixture
def mock_pi_agent_fn() -> MagicMock:
    return AsyncMock(
        return_value={
            "output": "O valor e 1523.4 Nm3/h",
            "error": None,
            "messages": [],
        }
    )


@pytest.fixture
def mock_general_agent_fn() -> MagicMock:
    return AsyncMock(
        return_value={
            "output": "Ola! Como posso ajudar?",
            "error": None,
            "messages": [],
        }
    )


@pytest.fixture
def mock_route_fn() -> MagicMock:
    class FakeRouterOutput:
        rota = "pims"

    return AsyncMock(return_value=FakeRouterOutput())
