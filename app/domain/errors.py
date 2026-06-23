"""Domain-level exceptions.

These represent business-rule violations, NOT infrastructure failures.
For infrastructure errors (timeouts, connection refused), use the
specific exception types from httpx, redis, etc.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain exceptions."""


class TagNotFoundError(DomainError):
    """A requested PI tag does not exist on the server."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        super().__init__(f"Tag not found: {tag}")


class InvalidTimeWindowError(DomainError):
    """A time window has invalid or inconsistent bounds."""

    def __init__(self, start: str, end: str, reason: str = "") -> None:
        self.start = start
        self.end = end
        msg = f"Invalid time window: start='{start}' end='{end}'"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class MathToolTimeoutError(DomainError):
    """The Math Tool service did not respond within the timeout."""

    def __init__(self, operation: str, timeout_seconds: float) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Math Tool timeout on '{operation}' after {timeout_seconds}s"
        )
