"""Base abstractions for Queries and Query Handlers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

Q = TypeVar("Q", bound="Query")
R = TypeVar("R")


@dataclass(frozen=True)
class Query:
    """Base class for all Queries.

    Queries are immutable, idempotent, and produce no side effects.
    """


@runtime_checkable
class QueryHandler(Protocol[Q, R]):
    """Protocol for Query Handlers.

    A handler receives a Query and returns data.
    """

    async def handle(self, query: Q) -> R: ...
