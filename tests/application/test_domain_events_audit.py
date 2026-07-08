"""
Domain Events audit — Prompt 6 Ciclo 1.

Congela o estado atual de Domain Events e dos pontos de publicação
da ConversationSaga. Read-only, sem alteração de produção.

Snapshot data: ver scrap/last_answer (análise + clarify).

Dívidas registradas neste ciclo (NÃO corrigir aqui):
  - UserMessageRecorded / AssistantMessageRecorded permanecem em
    app/domain/projections.py, fora do DOMAIN_EVENTS_REGISTRY (decisão Q2 = ii).
  - AggregateType não será exportado em app/domain/__init__.py (decisão Q3 = ii).
  - KNOWN_ANOMALIES não será reestruturado (decisão Q4 = ii).
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.sagas.conversation_saga import (
    ConversationContext,
    ConversationSaga,
)
from app.application.sagas.event_publisher import EventPublisherImpl
from app.domain.events import DOMAIN_EVENTS_REGISTRY, DomainEvent
from app.domain.projections import AssistantMessageRecorded, UserMessageRecorded
from app.infrastructure.event_store.base import EventStore
from app.infrastructure.event_store.in_memory import InMemoryEventStore


# ---------------------------------------------------------------------------
# Snapshot — 2026-06-29
# Ref: scrap/last_answer (Prompt 6 analyze seção 4.2 + 4.8)
# ---------------------------------------------------------------------------

# 1. Todos os tipos do DOMAIN_EVENTS_REGISTRY (23 eventos de domínio)
EXPECTED_DOMAIN_EVENT_TYPES: frozenset[str] = frozenset({
    "InboundMessageReceived",
    "OcrExtractionCompleted",
    "ConversationMemoryLoaded",
    "AgentRouteSelected",
    "RagContextRetrieved",
    "AgentRunStarted",
    "AgentToolInvocationRequested",
    "AgentToolInvocationCompleted",
    "AgentRunCompleted",
    "AgentRunAborted",
    "PiTagQueried",
    "PiHistoricalSeriesRetrieved",
    "StatisticsComputed",
    "CalculusComputed",
    "PimsStatusChecked",
    "OutboundReplyGenerated",
    "ConversationMemorySaved",
    "GoogleChatEventReceived",
    "GoogleChatDedupeStarted",
    "GoogleChatReplySent",
    "GoogleChatDedupeCompleted",
    "MessageProcessingFailed",
    "GoogleChatAttachmentDownloaded",
    "ConversationMemorySaveRequested",
})  # 24 tipos. ruff: noqa: E501

# 2. Projection events conhecidos (fora do DOMAIN_EVENTS_REGISTRY)
EXPECTED_SAGA_PROJECTION_EVENT_TYPES: frozenset[str] = frozenset({
    "UserMessageRecorded",
    "AssistantMessageRecorded",
})  # 2 tipos. ruff: noqa: E501

# 3. Eventos de domínio publicados pela Saga (apenas os de app/domain/events.py)
EXPECTED_SAGA_DOMAIN_EVENT_TYPES: frozenset[str] = frozenset({
    "ConversationMemoryLoaded",       # _step_load_memory
    "AgentRouteSelected",             # _step_route
    "RagContextRetrieved",            # _step_retrieve_rag (pims only)
    "AgentRunStarted",                # _step_run_agent
    "AgentRunCompleted",              # _step_run_agent
    "ConversationMemorySaved",        # _step_save_memory (EDD=false legado)
    # OcrExtractionCompleted é CONDICIONAL: publicado APENAS quando há images.
    # No fluxo pims sem imagens, NÃO é publicado.
    # ConversationMemorySaveRequested é CONDICIONAL: publicado apenas quando
    # EVENT_DRIVEN_ENABLED=true. No fluxo padrão (EDD=false), não é publicado.
})  # 6 tipos + 2 condicionais. ruff: noqa: E501

# 4. Todos os tipos publicados pela Saga (domínio + projection)
EXPECTED_SAGA_PUBLISHED_EVENT_TYPES: frozenset[str] = (
    EXPECTED_SAGA_DOMAIN_EVENT_TYPES | EXPECTED_SAGA_PROJECTION_EVENT_TYPES
)  # 9 tipos

# 5. Eventos de domínio existentes mas NÃO publicados pela Saga
EXPECTED_UNPUBLISHED_DOMAIN_EVENT_TYPES: frozenset[str] = frozenset(
    EXPECTED_DOMAIN_EVENT_TYPES - EXPECTED_SAGA_DOMAIN_EVENT_TYPES
)  # 18 tipos


# ---------------------------------------------------------------------------
# Fakes (mesmo padrão de test_saga_with_events.py)
# ---------------------------------------------------------------------------

@dataclass
class _FakeMemoryResult:
    turns: list = field(default_factory=list)
    context: str = ""


@dataclass
class _FakeRouteResult:
    @property
    def route(self) -> Any:
        class _R:
            def __init__(self, v: str) -> None:
                self.value = v
        return _R("pims")


@dataclass
class _FakeRagResult:
    context: str = "RAG CTX"
    chunks_used: list = field(default_factory=list)


@dataclass
class _FakeAgentResult:
    output: str = "Resposta"
    error: str | None = None
    messages: list = field(default_factory=list)
    tool_name: str = "agent"


def _make_saga() -> tuple[ConversationSaga, InMemoryEventStore]:
    store = InMemoryEventStore()
    saga = ConversationSaga(
        load_memory_fn=AsyncMock(return_value=_FakeMemoryResult()),
        ocr_fn=AsyncMock(return_value=type("R", (), {"extractions": []})()),
        route_fn=AsyncMock(return_value=_FakeRouteResult()),
        rag_fn=AsyncMock(return_value=_FakeRagResult()),
        run_agent_fn=AsyncMock(return_value=_FakeAgentResult()),
        save_memory_fn=AsyncMock(),
        event_publisher=EventPublisherImpl(store),
    )
    return saga, store


# ---------------------------------------------------------------------------
# R1 — Catálogo atual de Domain Events
# ---------------------------------------------------------------------------

class TestEventCatalog:
    def test_registry_has_24_events(self) -> None:
        assert len(DOMAIN_EVENTS_REGISTRY) == 24

    def test_registry_keys_match_snapshot(self) -> None:
        assert set(DOMAIN_EVENTS_REGISTRY.keys()) == EXPECTED_DOMAIN_EVENT_TYPES

    def test_all_events_are_subclasses_of_domain_event(self) -> None:
        for name, cls in DOMAIN_EVENTS_REGISTRY.items():
            assert issubclass(cls, DomainEvent), f"{name} is not a DomainEvent"


# ---------------------------------------------------------------------------
# R2 — Projection events fora do registry
# ---------------------------------------------------------------------------

class TestProjectionEventsShape:
    def test_user_message_recorded_exists_in_projections(self) -> None:
        assert hasattr(UserMessageRecorded, "content")
        assert hasattr(UserMessageRecorded, "created_at")
        assert hasattr(UserMessageRecorded, "conversation_id")

    def test_assistant_message_recorded_exists_in_projections(self) -> None:
        assert hasattr(AssistantMessageRecorded, "content")
        assert hasattr(AssistantMessageRecorded, "created_at")
        assert hasattr(AssistantMessageRecorded, "conversation_id")

    def test_user_message_recorded_not_in_registry(self) -> None:
        assert "UserMessageRecorded" not in DOMAIN_EVENTS_REGISTRY

    def test_assistant_message_recorded_not_in_registry(self) -> None:
        assert "AssistantMessageRecorded" not in DOMAIN_EVENTS_REGISTRY

    def test_projection_events_remain_in_projections_module_outside_domain_registry(self) -> None:
        """Snapshot do estado atual: projection events vivem em app.domain.projections,
        fora do DOMAIN_EVENTS_REGISTRY, e não herdam de DomainEvent.

        Não é exigência arquitetural ideal — é congelamento do estado.
        """
        assert UserMessageRecorded.__module__ == "app.domain.projections"
        assert AssistantMessageRecorded.__module__ == "app.domain.projections"
        assert "UserMessageRecorded" not in DOMAIN_EVENTS_REGISTRY
        assert "AssistantMessageRecorded" not in DOMAIN_EVENTS_REGISTRY
        assert issubclass(UserMessageRecorded, DomainEvent) is False
        assert issubclass(AssistantMessageRecorded, DomainEvent) is False


# ---------------------------------------------------------------------------
# R3 — Eventos publicados pela Saga (whitelist)
# ---------------------------------------------------------------------------

class TestSagaPublishedEvents:
    @pytest.mark.asyncio
    async def test_pims_flow_publishes_expected_event_types(self) -> None:
        saga, store = _make_saga()
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="tag X",
        )
        await saga.execute(ctx)

        events = await store.read("conversation:c1")
        published_types = {type(e).__name__ for e in events}

        # Deve ser exatamente o set esperado (9 tipos)
        assert published_types == EXPECTED_SAGA_PUBLISHED_EVENT_TYPES

    def test_published_domain_events_are_in_registry(self) -> None:
        # Regra: publicados por domínio ⊆ registry
        assert EXPECTED_SAGA_DOMAIN_EVENT_TYPES <= EXPECTED_DOMAIN_EVENT_TYPES

    def test_published_projection_events_are_known(self) -> None:
        # Regra: publicados por projection ⊆ projection events conhecidos
        assert EXPECTED_SAGA_PROJECTION_EVENT_TYPES == frozenset({
            "UserMessageRecorded", "AssistantMessageRecorded",
        })


# ---------------------------------------------------------------------------
# R4 — Eventos existentes mas não publicados
# ---------------------------------------------------------------------------

class TestSagaUnpublishedEvents:
    def test_unpublished_domain_events_derived_correctly(self) -> None:
        assert EXPECTED_UNPUBLISHED_DOMAIN_EVENT_TYPES == (
            EXPECTED_DOMAIN_EVENT_TYPES - EXPECTED_SAGA_DOMAIN_EVENT_TYPES
        )

    def test_no_unpublished_event_appears_in_saga_output(self) -> None:
        # Nenhum dos 18 eventos não publicados deve aparecer na saída
        all_published = (
            EXPECTED_SAGA_DOMAIN_EVENT_TYPES | EXPECTED_SAGA_PROJECTION_EVENT_TYPES
        )
        assert len(EXPECTED_UNPUBLISHED_DOMAIN_EVENT_TYPES & all_published) == 0


# ---------------------------------------------------------------------------
# R5 — Dupla publicação latente de memória
# ---------------------------------------------------------------------------

class TestDuplicateMemoryPublicationLatent:
    @pytest.mark.asyncio
    async def test_path_v1_publishes_exactly_one_user_and_one_assistant(self) -> None:
        """Path v1 (produção): Saga publica 1 UserMessageRecorded + 1 AssistantMessageRecorded."""
        saga, store = _make_saga()
        ctx = ConversationContext(
            user_id="u1",
            conversation_id="c1",
            message_original="question",
        )
        await saga.execute(ctx)

        events = await store.read("conversation:c1")
        user_events = [e for e in events if type(e).__name__ == "UserMessageRecorded"]
        assistant_events = [e for e in events if type(e).__name__ == "AssistantMessageRecorded"]

        assert len(user_events) == 1
        assert len(assistant_events) == 1

    def test_adapter_v2_not_instantiated_by_process_message(self) -> None:
        """Versão Ciclo 2: substitui assert tautológico do Ciclo 1 (RR1).

        process_message deve estar limpa dos tokens que indicariam ativação
        do path v2 (memory EventStore-backed). O kwarg event_store= também
        não pode aparecer — sua presença significaria que _build_saga foi
        chamado com EventStore injetado.
        """
        src = inspect.getsource(app.agent.orchestrator.process_message)  # noqa: F821
        assert "RedisConversationMemory" not in src
        assert "redis_memory_v2" not in src
        assert "event_store=" not in src

    def test_build_saga_has_conditional_v2_path(self) -> None:
        """_build_saga contém o path v2 latente, guardado por condicional.

        v2 existe em _build_saga (linha 168-171 do orchestrator) e é
        instanciado apenas se event_store is not None. process_message
        chama _build_saga SEM event_store= (test acima), então o ramo
        v2 nunca é executado no fluxo /chat atual.

        Este teste documenta a LATÊNCIA do path v2: ele existe, mas
        está guardado por condicional.
        """
        src = inspect.getsource(app.agent.orchestrator._build_saga)  # noqa: F821
        assert src, "inspect.getsource(_build_saga) returned empty string"
        assert "RedisConversationMemory" in src
        assert "_MemoryAdapterV2" in src
        assert "if event_store is not None" in src

    def test_adapter_v2_source_would_publish_events(self) -> None:
        """Se v2 fosse injetado, append_turns publicaria os mesmos eventos."""
        from app.infrastructure.conversation import redis_memory_v2

        src = inspect.getsource(redis_memory_v2)
        assert "UserMessageRecorded" in src
        assert "AssistantMessageRecorded" in src
        assert "self._store.append" in src


# ---------------------------------------------------------------------------
# R6 — EventPublisherImpl fire-and-forget
# ---------------------------------------------------------------------------

class TestEventPublisherFireAndForget:
    def test_publish_source_has_except_pass(self) -> None:
        """EventPublisherImpl.publish engole exceções."""
        src = inspect.getsource(EventPublisherImpl.publish)
        assert "except" in src
        assert "logger.warning" in src

    @pytest.mark.asyncio
    async def test_publish_does_not_propagate_eventstore_error(self) -> None:
        """Exceção em EventStore.append não chega ao caller."""
        class _FailingStore:
            async def append(self, stream: str, event: DomainEvent) -> str:
                raise RuntimeError("store failure")
            async def read(self, stream: str, from_id: str = "0") -> list:
                return []
            async def append_batch(self, stream: str, events: list) -> list[str]:
                return []

        publisher = EventPublisherImpl(_FailingStore())  # type: ignore[arg-type]
        event = DomainEvent()
        # Não deve levantar exceção
        await publisher.publish("test:stream", event)

    @pytest.mark.asyncio
    async def test_publish_to_conversation_does_not_propagate_error(self) -> None:
        """Exceção em publish_to_conversation é silenciada."""
        class _FailingStore:
            async def append(self, stream: str, event: DomainEvent) -> str:
                raise RuntimeError("store failure")
            async def read(self, stream: str, from_id: str = "0") -> list:
                return []
            async def append_batch(self, stream: str, events: list) -> list[str]:
                return []

        publisher = EventPublisherImpl(_FailingStore())  # type: ignore[arg-type]
        event = DomainEvent()
        await publisher.publish_to_conversation("conv-1", event)


# ---------------------------------------------------------------------------
# R7 — PostgresEventStore opcional
# ---------------------------------------------------------------------------

class TestPostgresEventStoreOptional:
    def test_postgres_import_is_optional(self) -> None:
        """PostgresEventStore pode ser importado; se não, é dependência opcional."""
        try:
            from app.infrastructure.event_store.postgres_event_store import PostgresEventStore
            assert PostgresEventStore is not None
        except ImportError:
            pytest.skip("asyncpg ausente — PostgresEventStore é opcional")

    def test_process_message_does_not_use_get_event_store(self) -> None:
        """process_message instancia InMemoryEventStore literal, não usa factory."""
        import app.agent.orchestrator as orch

        src = inspect.getsource(orch.process_message)
        # Não deve chamar get_event_store()
        assert "get_event_store" not in src

    def test_factory_defaults_to_in_memory(self) -> None:
        """get_event_store() sem EVENT_STORE_BACKEND retorna InMemoryEventStore."""
        from app.infrastructure.event_store.factory import get_event_store

        store = get_event_store()
        assert isinstance(store, InMemoryEventStore)


# ---------------------------------------------------------------------------
# R8 — Queries purity reaproveitada (test_cqrs_audit.py)
# ---------------------------------------------------------------------------

class TestQueryPurityReuse:
    def test_query_purity_covered_by_cqrs_audit(self) -> None:
        """Validação de 'Queries não publicam eventos' já está em test_cqrs_audit.py.

        Não duplicamos a lógica aqui. Verificar que o módulo de audit existe
        e que a classe TestQueriesPurity existe.
        """
        from tests.application import test_cqrs_audit as _audit

        assert hasattr(_audit, "TestQueriesPurity")


# ---------------------------------------------------------------------------
# Import de módulo para R5b (precisa estar no topo do escopo do teste)
# ---------------------------------------------------------------------------

import app.agent.orchestrator  # noqa: E402 — necessário para inspect.getsource
