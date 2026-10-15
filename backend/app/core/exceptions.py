"""Custom exceptions and standard error formats for FreightIQ API."""

from __future__ import annotations

from typing import Any, Optional


class FreightIQException(Exception):
    """Base exception for all FreightIQ domain errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class EntityNotFoundException(FreightIQException):
    """Raised when a requested resource does not exist."""

    def __init__(self, entity_name: str, entity_id: str):
        super().__init__(
            message=f"{entity_name} with identifier '{entity_id}' not found.",
            status_code=404,
            error_code="NOT_FOUND",
            details={"entity": entity_name, "id": entity_id},
        )


class ValidationException(FreightIQException):
    """Raised when data validation, file upload, or parameter checks fail."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class SecurityException(FreightIQException):
    """Raised when path traversal or unsafe file operations are detected."""

    def __init__(self, message: str = "Unsafe request or path traversal detected."):
        super().__init__(
            message=message,
            status_code=400,
            error_code="SECURITY_VIOLATION",
        )
