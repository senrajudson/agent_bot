"""Command: Classify user message into an agent route."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from app.application.commands.base import Command
from app.domain.enums import AgentRoute


@dataclass(frozen=True)
class RouteMessage(Command):
    """Request route classification for a user message."""

    user_message: str


@dataclass(frozen=True)
class RouteMessageResult:
    """Result of route classification."""

    route: AgentRoute


class RouteMessageHandler:
    """Classifies a user message into an AgentRoute using an LLM router.

    Delegates to a route_fn (injected callable) that wraps litellm.
    No direct dependency on litellm, httpx, or any infrastructure.

    The route_fn must have the signature:
        async def route_fn(user_message: str) -> Any  # RouterOutput
    """

    def __init__(
        self,
        route_fn: Callable[[str], Coroutine[Any, Any, Any]],
    ) -> None:
        self._route_fn = route_fn

    async def handle(self, command: RouteMessage) -> RouteMessageResult:
        result = await self._route_fn(user_message=command.user_message)
        rota = result.rota if hasattr(result, "rota") else str(result)
        return RouteMessageResult(route=AgentRoute(rota))
