"""Automatic best-effort audit coverage for authenticated Admin mutations."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from zhizhi_platform.audit import AdminAuditActor, AdminAuditWriter

logger = logging.getLogger(__name__)
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_AUDIT_JSON_BYTES = 64 * 1024
SENSITIVE_FIELD_MARKERS = (
    "password",
    "credential",
    "secret",
    "token",
    "api_key",
    "private_key",
)


class AdminMutationAuditMiddleware(BaseHTTPMiddleware):
    """Append sanitized records for successful authenticated mutations."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not _is_admin_mutation(request):
            return await call_next(request)
        request_summary, body_tenant_id = await _request_summary(request)
        response = await call_next(request)
        if 200 <= response.status_code < 400:
            await _append_audit_safely(
                request,
                response,
                request_summary=request_summary,
                body_tenant_id=body_tenant_id,
            )
        return response


def attach_admin_audit_context(
    request: Request,
    *,
    actor: AdminAuditActor,
    writer: AdminAuditWriter,
) -> None:
    request.state.admin_audit_actor = actor
    request.state.admin_audit_writer = writer


def _is_admin_mutation(request: Request) -> bool:
    return request.method in MUTATION_METHODS and request.url.path.startswith("/api/admin/")


async def _request_summary(request: Request) -> tuple[dict[str, object], str]:
    summary: dict[str, object] = {"method": request.method, "path": request.url.path}
    correlation_id = (
        request.headers.get("x-request-id") or request.headers.get("x-correlation-id") or ""
    ).strip()
    if correlation_id:
        summary["correlation_id"] = correlation_id[:128]
    if request.query_params:
        summary["query_fields"] = sorted(set(request.query_params.keys()))
    content_length = _content_length(request)
    content_type = request.headers.get("content-type", "").lower()
    if (
        "application/json" not in content_type
        or content_length is None
        or content_length > MAX_AUDIT_JSON_BYTES
    ):
        return summary, ""
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return summary, ""
    if not isinstance(payload, dict):
        return summary, ""
    fields = sorted(str(field) for field in payload)
    summary["changed_fields"] = fields
    sensitive_fields = [field for field in fields if _is_sensitive_field(field)]
    if sensitive_fields:
        summary["sensitive_fields_changed"] = sensitive_fields
    return summary, str(payload.get("tenant_id") or "").strip()


async def _append_audit_safely(
    request: Request,
    response: Response,
    *,
    request_summary: dict[str, object],
    body_tenant_id: str,
) -> None:
    actor = getattr(request.state, "admin_audit_actor", None)
    writer = getattr(request.state, "admin_audit_writer", None)
    if not isinstance(actor, AdminAuditActor) or not isinstance(writer, AdminAuditWriter):
        return
    route = request.scope.get("route")
    route_path = str(getattr(route, "path", request.url.path))
    path_params = {str(key): str(value) for key, value in request.path_params.items()}
    target_id = next(
        (value for key, value in reversed(tuple(path_params.items())) if key.endswith("_id")),
        route_path,
    )
    target_tenant_id = (
        path_params.get("tenant_id")
        or request.query_params.get("tenant_id")
        or body_tenant_id
        or None
    )
    try:
        await writer.write(
            actor=actor,
            action=f"admin.http.{request.method.lower()}",
            target_resource_type=route_path,
            target_resource_id=target_id,
            target_tenant_id=target_tenant_id,
            scope_summary={**request_summary, "path_params": path_params},
            after_summary={"status_code": response.status_code},
        )
    except Exception as exc:
        logger.error(
            "Failed to append automatic Admin mutation audit method=%s route=%s "
            "exception_type=%s",
            request.method,
            route_path,
            type(exc).__name__,
        )


def _content_length(request: Request) -> int | None:
    value = request.headers.get("content-length")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _is_sensitive_field(field: str) -> bool:
    normalized = field.casefold()
    return any(marker in normalized for marker in SENSITIVE_FIELD_MARKERS)
