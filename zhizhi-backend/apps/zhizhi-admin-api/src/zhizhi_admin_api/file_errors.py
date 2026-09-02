"""HTTP translation for expected managed-file operation errors."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute

from zhizhi_platform.iam.errors import PermissionDeniedError
from zhizhi_platform.workspace import ConflictError, UnsupportedFileError


class AdminFileErrorRoute(APIRoute):
    """Translate expected repository file errors into stable Admin API responses."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def translated_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="Path does not exist.") from exc
            except (IsADirectoryError, NotADirectoryError, FileExistsError, ConflictError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail="File operation conflicts with the current path state.",
                ) from exc
            except (PermissionDeniedError, PermissionError) as exc:
                raise HTTPException(
                    status_code=403,
                    detail="File operation is not permitted.",
                ) from exc
            except UnsupportedFileError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return translated_handler
