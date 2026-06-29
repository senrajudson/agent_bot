"""Command: Run the agent or general agent for a user message."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from app.application.commands.base import Command
from app.domain.enums import AgentRoute


@dataclass(frozen=True)
class RunAgentForMessage(Command):
    """Request agent execution for a user message."""

    user_message: str
    user_id: str
    session_id: str
    route: AgentRoute
    memory_context: str | None = None


@dataclass(frozen=True)
class RunAgentForMessageResult:
    """Result of agent execution."""

    output: str
    error: str | None
    messages: list[dict[str, Any]]
    tool_name: str


class RunAgentForMessageHandler:
    """Runs the appropriate agent (PI or General) for a user message.

    Delegates to agent_fn (injected callable) that wraps agent or general_agent.
    No direct dependency on litellm, httpx, google.adk, or any infrastructure.

    The agent_fn must have the signature:
        async def agent_fn(user_message: str, ...) -> dict[str, Any]
    """

    def __init__(
        self,
        agent_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
        general_agent_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> None:
        self._agent_fn = agent_fn
        self._general_agent_fn = general_agent_fn

    async def handle(
        self, command: RunAgentForMessage
    ) -> RunAgentForMessageResult:
        if command.route == AgentRoute.PIMS:
            result = await self._agent_fn(
                user_message=command.user_message,
                user_id=command.user_id,
                session_id=command.session_id,
            )
            tool_name = "agent"
        else:
            result = await self._general_agent_fn(
                user_message=command.user_message,
                memory_context=command.memory_context,
            )
            tool_name = "general_agent"

        return RunAgentForMessageResult(
            output=result.get("output", ""),
            error=result.get("error"),
            messages=result.get("messages", []),
            tool_name=tool_name,
        )
