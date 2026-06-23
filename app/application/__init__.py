"""Application layer — Commands, Queries, and their Handlers.

This package orchestrates domain operations. Handlers receive
Commands/Queries and delegate to infrastructure (Protocols).
"""
from __future__ import annotations

from app.application.commands.base import Command, CommandHandler
from app.application.queries.base import Query, QueryHandler

__all__ = [
    "Command",
    "CommandHandler",
    "Query",
    "QueryHandler",
]
