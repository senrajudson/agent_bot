"""Command: Invoke an MCP tool via the ADK gateway."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.commands.base import Command


@dataclass(frozen=True)
class InvokeMcpTool(Command):
    """Request invocation of an MCP tool.

    NOTE: This is a PLACEHOLDER for Etapa 5 (Event Store).
    The actual MCP invocation happens inside ADK's McpToolset
    (via app/agent/pi_agent.py). In Etapa 5, this will be replaced
    by a proper Command bus.
    """

    tool_name: str
    args: dict


@dataclass(frozen=True)
class InvokeMcpToolResult:
    """Result of MCP tool invocation."""

    output: str
    success: bool


class InvokeMcpToolHandler:
    """Placeholder handler for MCP tool invocation.

    The real implementation routes through the Event Store (Etapa 5).
    For now, this handler raises NotImplementedError to signal that
    MCP invocation is still delegated to ADK directly.
    """

    async def handle(self, command: InvokeMcpTool) -> InvokeMcpToolResult:
        raise NotImplementedError(
            "InvokeMcpToolHandler is a placeholder. "
            "MCP invocation is delegated to ADK (app/agent/pi_agent.py). "
            "Etapa 5 will implement this via Event Store."
        )
