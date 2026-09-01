"""Stable Zhizhi Workspace domain failures independent of HTTP."""


class WorkspaceDomainError(Exception):
    """Base class for expected Workspace domain failures."""


class ConflictError(WorkspaceDomainError):
    """Raised when optimistic or physical state prevents a mutation."""


class UnsupportedFileError(WorkspaceDomainError):
    """Raised when a managed text file violates its contract."""
