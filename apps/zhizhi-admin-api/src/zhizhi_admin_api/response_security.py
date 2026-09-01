"""Security headers for management API responses."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class AdminNoStoreMiddleware(BaseHTTPMiddleware):
    """Prevent browsers and shared proxies from caching Admin API responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/admin/"):
            response.headers["Cache-Control"] = "private, no-store"
        return response


__all__ = ["AdminNoStoreMiddleware"]
