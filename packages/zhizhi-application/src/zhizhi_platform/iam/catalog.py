"""Hard bounds for IAM catalogs that must be returned completely."""

from collections.abc import Callable, Sequence

from gewu_core.errors import ApplicationError, ApplicationErrorKind

DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES = 1_000


def project_complete_catalog[RowT, ResultT](
    rows: Sequence[RowT],
    projector: Callable[[RowT], ResultT],
    *,
    max_entries: int,
    capacity_message: str,
) -> list[ResultT]:
    """Project all rows or fail instead of silently truncating authorization state."""

    if max_entries < 1:
        raise ValueError("max_entries must be greater than zero")
    if len(rows) > max_entries:
        raise ApplicationError(ApplicationErrorKind.UNAVAILABLE, capacity_message)
    return [projector(row) for row in rows]
