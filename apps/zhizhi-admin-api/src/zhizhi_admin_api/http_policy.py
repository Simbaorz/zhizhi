"""HTTP capacity and request-size policy for 致知 management routes."""

from __future__ import annotations

from starlette.types import Scope

from zhizhi_admin_api.settings import AdminApiSettings

_UPLOAD_SUFFIXES = frozenset({"upload", "package", "directory-package"})
_ADMIN_PREFIX = "/api/admin/"
_WEB_UPLOAD_PREFIXES = ("/api/workspace/", "/api/scenes/", "/api/skills/")
_FOREIGN_USER_JSON_MAX_BYTES = 256 * 1024
_FOREIGN_CHAT_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def admin_request_body_limit(scope: Scope) -> int | None:
    """Return the byte limit for one 致知 Admin request body."""

    path = str(scope.get("path") or "")
    if is_admin_upload_request(scope) or _is_foreign_web_upload_request(scope):
        return None
    if path.startswith("/api/admin"):
        return _admin_settings(scope).http_ingress.admin_json_max_bytes
    if path == "/api/chat/attachments":
        return _FOREIGN_USER_JSON_MAX_BYTES + _FOREIGN_CHAT_MULTIPART_OVERHEAD_BYTES
    if not path.startswith("/api/"):
        return None
    return _FOREIGN_USER_JSON_MAX_BYTES


def is_admin_upload_request(scope: Scope) -> bool:
    """Select 致知 Admin upload routes for ingress capacity control."""

    if scope["type"] != "http":
        return False
    method = str(scope.get("method") or "").upper()
    path = str(scope.get("path") or "").rstrip("/")
    if method != "PUT":
        return False
    suffix = path.rsplit("/", maxsplit=1)[-1]
    return suffix in _UPLOAD_SUFFIXES and path.startswith(_ADMIN_PREFIX)


def is_admin_download_request(scope: Scope) -> bool:
    """Select 致知 Admin download routes for egress capacity control."""

    if scope["type"] != "http":
        return False
    method = str(scope.get("method") or "").upper()
    if method not in {"GET", "HEAD"}:
        return False
    path = str(scope.get("path") or "").rstrip("/")
    return path.endswith("/download") and path.startswith(_ADMIN_PREFIX)


def _is_foreign_web_upload_request(scope: Scope) -> bool:
    method = str(scope.get("method") or "").upper()
    path = str(scope.get("path") or "").rstrip("/")
    if method == "POST" and path == "/api/chat/attachments":
        return False
    if method != "PUT":
        return False
    suffix = path.rsplit("/", maxsplit=1)[-1]
    return suffix in _UPLOAD_SUFFIXES and path.startswith(_WEB_UPLOAD_PREFIXES)


def _admin_settings(scope: Scope) -> AdminApiSettings:
    state = getattr(scope.get("app"), "state", None)
    runtime = getattr(state, "runtime", None)
    settings = getattr(runtime, "settings", None)
    return settings if isinstance(settings, AdminApiSettings) else AdminApiSettings()
