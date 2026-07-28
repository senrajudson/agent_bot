from __future__ import annotations

from enum import Enum


class ValidationErrorCode(str, Enum):
    INVALID_GROUP_BY = "INVALID_GROUP_BY"
    INVALID_DATA_METHOD = "INVALID_DATA_METHOD"
    INVALID_ARGUMENT_COMBINATION = "INVALID_ARGUMENT_COMBINATION"


class DomainValidationError(ValueError):
    def __init__(self, code: ValidationErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)
