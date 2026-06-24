"""Event Store errors."""


class ConcurrencyConflictError(Exception):
    """Raised when an optimistic concurrency check fails.

    Occurs when ``expected_version`` does not match the current
    ``stream_version`` of the target stream.
    """

    def __init__(self, stream_id: str, expected_version: int, actual_version: int) -> None:
        self.stream_id = stream_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Concurrency conflict on stream '{stream_id}': "
            f"expected version {expected_version}, got {actual_version}"
        )
