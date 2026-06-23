"""Base abstractions for Commands and Command Handlers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, runtime_checkable

C = TypeVar("C", bound="Command")
R = TypeVar("R")


@dataclass(frozen=True)
class Command:
    """Base class for all Commands.

    Commands are immutable, represent intent to perform an action,
    and may produce side effects.
    """


@runtime_checkable
class CommandHandler(Protocol[C, R]):
    """Protocol for Command Handlers.

    A handler receives a Command and returns a Result.
    Handlers are thin — they orchestrate domain operations and
    delegate to infrastructure (repositories, services).
    """

    async def handle(self, command: C) -> R: ...
