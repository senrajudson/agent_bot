class ArtifactDeliveryError(Exception):
    pass


class ArtifactLimitExceededError(ArtifactDeliveryError):
    def __init__(
        self,
        field: str,
        limit: int | float,
        actual: int | float,
    ) -> None:
        self.field = field
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Limite de artefato excedido: {field}={actual} (máximo {limit}). "
            f"Reduza o período, o número de tags ou a granularidade."
        )


class DriveConfigError(ArtifactDeliveryError):
    pass


class ManifestSizeExceededError(ArtifactDeliveryError):
    pass


class InlinePayloadTooLargeError(ArtifactDeliveryError):
    def __init__(
        self,
        tool_name: str,
        size_bytes: int,
        max_bytes: int,
    ) -> None:
        self.tool_name = tool_name
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(
            f"[INLINE_PAYLOAD_TOO_LARGE] "
            f"tool={tool_name} size_bytes={size_bytes} max_bytes={max_bytes}"
        )


class ArtifactDeliveryDisabledError(ArtifactDeliveryError):
    def __init__(
        self,
        tool_name: str,
        output_mode: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.output_mode = output_mode
        mode_str = f" mode={output_mode}" if output_mode else ""
        super().__init__(
            f"[ARTIFACT_DELIVERY_DISABLED] "
            f"tool={tool_name}{mode_str} - "
            f"A entrega automática de artefatos está desabilitada. "
            f"Séries temporais não podem ser retornadas inline."
        )


class DeliveryRejectedError(ArtifactDeliveryError):
    def __init__(
        self,
        tool_name: str,
        reason_code: str,
        reason: str,
    ) -> None:
        self.tool_name = tool_name
        self.reason_code = reason_code
        self.reason = reason
        super().__init__(
            f"[{reason_code}] tool={tool_name} - {reason}"
        )
