"""致知 IAM domain failures independent from inbound transports."""

from gewu_core import ApplicationError, ApplicationErrorKind


class DomainError(ValueError):
    """Base error raised by 致知 IAM domain rules."""


class PermissionDeniedError(DomainError):
    """The active 致知 principal cannot access the requested scope."""


class AuthorizationCatalogCapacityExceededError(ApplicationError):
    """Reject an authorization result that cannot be returned completely."""

    def __init__(self, catalog: str, limit: int) -> None:
        super().__init__(
            ApplicationErrorKind.UNAVAILABLE,
            f"{catalog} contains more than {limit} entries. Please contact an administrator.",
        )


class OrganizationDirectoryCapacityExceededError(ApplicationError):
    """Reject an internal area lookup that cannot remain complete."""

    def __init__(self, operation: str, limit: int) -> None:
        super().__init__(
            ApplicationErrorKind.UNAVAILABLE,
            f"{operation} contains more than {limit} areas. Please narrow the request.",
        )
