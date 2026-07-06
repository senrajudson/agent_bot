"""EventTypeRouterConsumer — roteia OutboxEvent por event_type para handlers específicos.

Camada intermediária entre o OutboxDispatcher e os consumers de cada event_type.
Quando o event_type não tem handler registrado, delega ao fallback.

Composição:
  OutboxDispatcher
    → EventTypeRouterConsumer
        ├── handler específico (se event_type ∈ handlers)
        └── fallback (caso contrário)

O router não constrói fallback internamente.
O fallback é recebido pronto no construtor e é obrigatório.
O router não tem consumer_name próprio — usa o consumer_name do OutboxDispatcher.
"""
from __future__ import annotations

import logging
from typing import Mapping

from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent, OutboxConsumer

logger = logging.getLogger("app.infrastructure.outbox.event_type_router_consumer")


class EventTypeRouterConsumer:
    """Roteia OutboxEvent para handler específico ou fallback.

    Attributes:
        handlers: Mapa event_type → handler. Pode ser vazio.
        fallback: Consumer chamado quando event_type não está em handlers.
            Obrigatório, não pode ser None.
    """

    def __init__(
        self,
        handlers: Mapping[str, OutboxConsumer] | None = None,
        fallback: OutboxConsumer | None = None,
    ) -> None:
        if fallback is None:
            raise ValueError("fallback is required")
        if handlers is None:
            handlers = {}
        self._handlers: dict[str, OutboxConsumer] = dict(handlers)
        self._fallback: OutboxConsumer = fallback

    async def handle(self, event: OutboxEvent) -> None:
        handler = self._handlers.get(event.event_type, self._fallback)
        await handler.handle(event)
