"""Stable Zhizhi domain and application errors independent from HTTP transports."""

from __future__ import annotations

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.errors import (
    AuthorizationCatalogCapacityExceededError,
    DomainError,
    PermissionDeniedError,
)

__all__ = [
    "ApplicationError",
    "ApplicationErrorKind",
    "AuthorizationCatalogCapacityExceededError",
    "DomainError",
    "PermissionDeniedError",
]
