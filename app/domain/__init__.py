"""
Domain layer — pure abstractions and value objects.

This package has NO dependencies on infrastructure (httpx, redis, qdrant).
Concrete implementations live in app/clients/ and app/services/.
"""
from app.domain.errors import (
    DomainError,
    InvalidTimeWindowError,
    MathToolTimeoutError,
    TagNotFoundError,
)
from app.domain.enums import (
    AgentRoute,
    CalculusOperation,
    PointType,
    StatisticalOperation,
    TemporalDataMethod,
)
from app.domain.protocols import (
    ConversationMemory,
    KnowledgeRepository,
    MathToolClient,
    OcrService,
    PIPointRepository,
    PimsOpsRepository,
)
from app.domain.value_objects import (
    CalculationBasis,
    CalculationBasisValue,
    ConversationId,
    EngineeringUnit,
    PiWebId,
    SummaryType,
    SummaryTypeValue,
    TimeUnit,
    TimeUnitValue,
    TimeWindow,
)

__all__ = [
    # Errors
    "DomainError",
    "TagNotFoundError",
    "InvalidTimeWindowError",
    "MathToolTimeoutError",
    # Enums
    "PointType",
    "TemporalDataMethod",
    "CalculusOperation",
    "StatisticalOperation",
    "AgentRoute",
    # Protocols
    "PIPointRepository",
    "KnowledgeRepository",
    "ConversationMemory",
    "OcrService",
    "MathToolClient",
    "PimsOpsRepository",
    # Value Objects
    "PiWebId",
    "EngineeringUnit",
    "TimeWindow",
    "TimeUnit",
    "TimeUnitValue",
    "SummaryType",
    "SummaryTypeValue",
    "CalculationBasis",
    "CalculationBasisValue",
    "ConversationId",
]
