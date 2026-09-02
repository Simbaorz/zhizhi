"""致知 Admin HTTP request classification policy."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from starlette.types import Scope

from zhizhi_admin_api.http_policy import (
    admin_request_body_limit,
    is_admin_download_request,
    is_admin_upload_request,
)
from zhizhi_admin_api.settings import AdminApiSettings, AdminHttpIngressSettings


def test_admin_body_limit_preserves_json_and_upload_policy() -> None:
    settings = AdminApiSettings(http_ingress=AdminHttpIngressSettings(admin_json_max_bytes=2_048))

    assert admin_request_body_limit(_scope("POST", "/api/admin/users", settings)) == 2_048
    assert (
        admin_request_body_limit(_scope("PUT", "/api/admin/skill-files/upload", settings)) is None
    )
    assert admin_request_body_limit(_scope("POST", "/external", settings)) is None


def test_admin_body_limits_preserve_foreign_web_route_error_priority() -> None:
    settings = AdminApiSettings(http_ingress=AdminHttpIngressSettings(admin_json_max_bytes=2_048))

    assert admin_request_body_limit(_scope("POST", "/api/items", settings)) == 256 * 1024
    assert admin_request_body_limit(_scope("POST", "/api/chat/stream", settings)) == 256 * 1024
    assert admin_request_body_limit(_scope("POST", "/api/chat/attachments", settings)) == 320 * 1024
    assert admin_request_body_limit(_scope("PUT", "/api/workspace/upload", settings)) is None


def test_admin_upload_and_download_selectors_own_only_admin_routes() -> None:
    assert is_admin_upload_request(_scope("PUT", "/api/admin/skill-files/upload"))
    assert is_admin_upload_request(_scope("PUT", "/api/admin/scenes/S1/package"))
    assert not is_admin_upload_request(_scope("PUT", "/api/workspace/upload"))

    assert is_admin_download_request(_scope("GET", "/api/admin/skill-files/download"))
    assert is_admin_download_request(_scope("HEAD", "/api/admin/scenes/S1/download"))
    assert not is_admin_download_request(_scope("GET", "/api/workspace/download"))


def _scope(
    method: str,
    path: str,
    settings: AdminApiSettings | None = None,
) -> Scope:
    app = SimpleNamespace(
        state=SimpleNamespace(runtime=SimpleNamespace(settings=settings or AdminApiSettings()))
    )
    return cast(Scope, {"type": "http", "method": method, "path": path, "app": app})
