"""Dedicated 致知 Admin API process behavior."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from gewu_core.config import BootstrapSettings
from gewu_core.database import DatabaseRuntime
from gewu_core.http import PasswordTransportSettings
from gewu_core.secrets import StorageEncryptionSettings
from zhizhi_admin_api import runtime as runtime_module
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.dependencies import (
    get_admin_auth_service,
    get_admin_user_admin_service,
    get_current_admin_session,
    get_data_source_admin_service,
    get_git_admin_service,
    get_llm_admin_service,
    get_organization_admin_service,
    get_role_admin_service,
    get_scene_admin_service,
    get_skill_admin_service,
    get_tenant_member_admin_service,
)
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiBootstrapSettings, AdminApiSettings
from zhizhi_platform.iam import ADMIN_PERMISSION_SEEDS, JwtSettings
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminUserModel,
)

PASSWORD_KEY_CONTRACT_SHA256 = "004613a2ac0a3306be5484585374fb31c74e178ef07a11c992e8afb395489b0d"
AUTH_CONTRACT_SHA256 = "e68c4f349fe5579c207e645150f40a2ae81fda6c7dce2e43a8f8129e0cf3a1d7"


@pytest.mark.parametrize(
    ("dependency", "detail"),
    [
        (get_admin_auth_service, "Admin auth service is not configured."),
        (get_admin_user_admin_service, "Admin user management service is not configured."),
        (get_role_admin_service, "Role management service is not configured."),
        (get_organization_admin_service, "Organization service is not configured."),
        (
            get_tenant_member_admin_service,
            "Tenant member management service is not configured.",
        ),
        (get_git_admin_service, "Git management service is not configured."),
        (get_llm_admin_service, "LLM management service is not configured."),
        (
            get_data_source_admin_service,
            "Data source management service is not configured.",
        ),
        (get_skill_admin_service, "Skill management service is not configured."),
        (get_scene_admin_service, "Scene management service is not configured."),
    ],
)
def test_admin_service_dependency_failures_match_zhizhi_contract(
    dependency: Callable[[Request], object],
    detail: str,
) -> None:
    app = FastAPI()
    app.state.runtime = SimpleNamespace()
    request = Request({"type": "http", "app": app})

    with pytest.raises(HTTPException) as error:
        dependency(request)

    assert error.value.status_code == 503
    assert error.value.detail == detail


def test_admin_app_owns_a_started_runtime_and_health_contract(tmp_path: Path) -> None:
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(bootstrap, settings=AdminApiSettings())
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "reasons": []}
    assert set(app.openapi()["paths"]) == {
        "/api/admin/auth/password-key",
        "/api/admin/auth/login",
        "/api/admin/auth/logout",
        "/api/admin/auth/me",
        "/api/admin/auth/me/profile",
        "/api/admin/auth/me/password",
        "/api/admin/auth/navigation",
        "/api/admin/bootstrap",
        "/api/admin/bootstrap/status",
        "/api/admin/data-sources/bindings",
        "/api/admin/data-sources/bindings/{binding_id}",
        "/api/admin/data-sources/entitlements",
        "/api/admin/data-sources/entitlements/{entitlement_id}",
        "/api/admin/data-sources/sources",
        "/api/admin/data-sources/sources/{source_id}",
        "/api/admin/roles",
        "/api/admin/roles/{role_id}",
        "/api/admin/roles/{role_id}/permissions",
        "/api/admin/permissions",
        "/api/admin/tenant-members/assignable-roles",
        "/api/admin/tenant-members",
        "/api/admin/tenant-members/{member_id}",
        "/api/admin/users/tenant-admins",
        "/api/admin/users/create-or-bind",
        "/api/admin/users/{user_id}",
        "/api/admin/users/{user_id}/reset-password",
        "/api/admin/scope-catalog",
        "/api/admin/git-repositories",
        "/api/admin/git-repositories/{repository_id}",
        "/api/admin/git-repositories/{repository_id}/credentials",
        "/api/admin/git-repositories/{repository_id}/test",
        "/api/admin/git-repositories/entitlements/list",
        "/api/admin/git-repositories/entitlements/batch",
        "/api/admin/git-repositories/entitlements/{entitlement_id}",
        "/api/admin/git-repositories/available/list",
        "/api/admin/llm/models",
        "/api/admin/llm/models/{model_id}",
        "/api/admin/llm/models/{model_id}/credentials",
        "/api/admin/llm/models/{model_id}/validate",
        "/api/admin/llm/models/{model_id}/test",
        "/api/admin/llm/bindings",
        "/api/admin/llm/bindings/{binding_id}",
        "/api/admin/llm/entitlements",
        "/api/admin/llm/entitlements/batch",
        "/api/admin/llm/entitlements/{entitlement_id}",
        "/api/admin/org/tenants",
        "/api/admin/org/tenants/{tenant_id}",
        "/api/admin/org/tenants/{tenant_id}/organization-units",
        "/api/admin/org/organization-units/{organization_unit_id}",
        "/api/admin/scenes",
        "/api/admin/scenes/directories",
        "/api/admin/scenes/directory-package",
        "/api/admin/scenes/download",
        "/api/admin/scenes/entries",
        "/api/admin/scenes/file",
        "/api/admin/scenes/git",
        "/api/admin/scenes/move",
        "/api/admin/scenes/package",
        "/api/admin/scenes/path",
        "/api/admin/scenes/upload",
        "/api/admin/scenes/sync-jobs/{job_id}",
        "/api/admin/scenes/{scene_asset_key}",
        "/api/admin/scenes/{scene_asset_key}/git",
        "/api/admin/scenes/{scene_asset_key}/package",
        "/api/admin/scenes/{scene_asset_key}/sync",
        "/api/admin/scenes/{scene_asset_key}/sync-jobs",
        "/api/admin/skill-files",
        "/api/admin/skill-files/directories",
        "/api/admin/skill-files/download",
        "/api/admin/skill-files/entries",
        "/api/admin/skill-files/file",
        "/api/admin/skill-files/move",
        "/api/admin/skill-files/package",
        "/api/admin/skill-files/upload",
        "/api/admin/skills",
        "/api/admin/skills/package",
        "/api/admin/skills/{skill_asset_key}",
        "/api/admin/skills/{skill_asset_key}/package",
    }

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            permissions = list(session.scalars(select(AdminPermissionModel)))
            users = list(session.scalars(select(AdminUserModel)))
    finally:
        engine.dispose()
    assert len(permissions) == len(ADMIN_PERMISSION_SEEDS)
    assert users == []


async def test_admin_runtime_loads_apollo_once_without_monitoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    settings = AdminApiSettings()

    async def load_once(*_args: object, **_kwargs: object) -> AdminApiSettings:
        events.append("load")
        return settings

    bootstrap = AdminApiBootstrapSettings(
        PROJECT_HOME=tmp_path,
        CONFIG_SOURCE="apollo",
        APOLLO_BASE_URL="http://apollo.test",
        APOLLO_APP_ID="zhizhi-admin-api",
    )
    runtime = ZhizhiAdminApiRuntime(bootstrap)

    async def start_components(resolved: AdminApiSettings) -> None:
        assert resolved is settings
        runtime._started = True

    monkeypatch.setattr(runtime_module, "load_settings_once", load_once)
    monkeypatch.setattr(runtime, "_startup_components", start_components)

    await runtime.startup()
    await runtime.shutdown()

    assert runtime.settings is settings
    assert events == ["load"]


async def test_admin_runtime_validates_security_before_creating_database(tmp_path: Path) -> None:
    key_path = tmp_path / "password.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    bootstrap = AdminApiBootstrapSettings(
        PROJECT_HOME=tmp_path,
        ENFORCE_STRONG_SECRETS=True,
    )
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk="short"),
            storage_encryption=StorageEncryptionSettings(key="another-short-secret"),
            password_transport=PasswordTransportSettings(private_key_path=str(key_path)),
        ),
    )

    with pytest.raises(RuntimeError, match="jwt.sk must contain at least"):
        await runtime.startup()

    assert not (tmp_path / "zhizhi.db").exists()
    assert runtime._database is None
    assert runtime._redis is None
    assert runtime._http is None


async def test_admin_runtime_rolls_back_resources_when_startup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_shutdowns = 0
    original_shutdown = DatabaseRuntime.shutdown

    async def tracked_database_shutdown(database: DatabaseRuntime) -> None:
        nonlocal database_shutdowns
        database_shutdowns += 1
        await original_shutdown(database)

    async def fail_seed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("seed failed")

    monkeypatch.setattr(DatabaseRuntime, "shutdown", tracked_database_shutdown)
    monkeypatch.setattr(runtime_module, "seed_admin_security", fail_seed)
    runtime = ZhizhiAdminApiRuntime(
        BootstrapSettings(PROJECT_HOME=tmp_path),
        settings=AdminApiSettings(),
    )

    with pytest.raises(RuntimeError, match="seed failed"):
        await runtime.startup()

    assert database_shutdowns == 1
    assert runtime._database is None
    assert runtime._iam is None
    assert runtime._redis is None
    assert runtime._http is None


def test_admin_app_publishes_its_explicit_cookie_security_policy(tmp_path: Path) -> None:
    app = create_admin_app(
        bootstrap=AdminApiBootstrapSettings(
            PROJECT_HOME=tmp_path,
            ADMIN_SESSION_COOKIE_SECURE=True,
        )
    )

    assert app.state.admin_session_cookie_secure is True


def test_admin_password_key_route_uses_startup_loaded_keyring(tmp_path: Path) -> None:
    app = _app_with_password_transport(tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/admin/auth/password-key")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["algorithm"] == "RSA-OAEP-256"
    assert len(response.json()["key_id"]) == 16
    assert "BEGIN PUBLIC KEY" in response.json()["public_key_pem"]


def test_admin_password_key_openapi_matches_zhizhi_baseline() -> None:
    openapi = create_admin_app().openapi()
    contract = {"path": openapi["paths"]["/api/admin/auth/password-key"]}
    payload = json.dumps(
        contract,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()

    assert hashlib.sha256(payload).hexdigest() == PASSWORD_KEY_CONTRACT_SHA256


def test_complete_admin_auth_openapi_matches_zhizhi_baseline() -> None:
    assert _contract_hash(create_admin_app().openapi(), "/api/admin/auth") == AUTH_CONTRACT_SHA256


def test_complete_admin_openapi_publishes_the_management_surface() -> None:
    spec = create_admin_app().openapi()
    paths = set(spec["paths"])

    assert spec["info"]["title"] == "致知 Admin API"
    assert "/api/admin/org/tenants/{tenant_id}/organization-units" in paths
    assert "/api/admin/llm/bindings" in paths
    assert "/api/admin/data-sources/bindings" in paths
    assert "/api/admin/scenes" in paths
    assert "/api/admin/skills" in paths
    assert not any("/areas" in path for path in paths)


def test_all_admin_routes_publish_success_response_schemas() -> None:
    openapi = create_admin_app().openapi()
    operations = [
        operation
        for path, path_item in openapi["paths"].items()
        if path.startswith("/api/admin/")
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]

    assert operations
    assert all(
        any(media["schema"] for media in operation["responses"]["200"]["content"].values())
        for operation in operations
    )


def test_all_admin_request_models_forbid_unknown_fields() -> None:
    schemas = create_admin_app().openapi()["components"]["schemas"]
    request_schemas = [
        schema
        for name, schema in schemas.items()
        if name.endswith("Request") or name.endswith("Payload")
    ]

    assert request_schemas
    assert all(schema.get("additionalProperties") is False for schema in request_schemas)


def test_admin_mutations_publish_cookie_and_csrf_contract() -> None:
    openapi = create_admin_app().openapi()
    mutations = [
        operation
        for path, path_item in openapi["paths"].items()
        if path not in {"/api/admin/auth/login", "/api/admin/bootstrap"}
        for method, operation in path_item.items()
        if method in {"post", "put", "patch", "delete"}
    ]

    assert mutations
    security_scheme = openapi["components"]["securitySchemes"]["AdminSessionCookie"]
    assert security_scheme == {
        "type": "apiKey",
        "description": "HttpOnly Admin session Cookie established by the login endpoint.",
        "in": "cookie",
        "name": "zhizhi_admin_session",
    }
    for operation in mutations:
        parameters = operation.get("parameters", [])
        assert {"AdminSessionCookie": []} in operation.get("security", [])
        assert any(
            parameter.get("in") == "header" and parameter.get("name") == "X-CSRF-Token"
            for parameter in parameters
        )


def test_admin_login_response_has_an_explicit_token_free_schema() -> None:
    openapi = create_admin_app().openapi()
    response_schema = openapi["paths"]["/api/admin/auth/login"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    assert response_schema == {"$ref": "#/components/schemas/AdminLoginResponse"}
    schema = openapi["components"]["schemas"]["AdminLoginResponse"]
    assert schema["additionalProperties"] is False
    assert "token" not in schema["properties"]
    assert set(schema["required"]) == {
        "user",
        "roles",
        "permissions",
        "tenant_members",
        "navigation",
    }


def test_all_nonpublic_admin_routes_require_an_admin_session() -> None:
    public_paths = {
        "/api/admin/auth/password-key",
        "/api/admin/auth/login",
        "/api/admin/bootstrap",
        "/api/admin/bootstrap/status",
    }
    unprotected_routes = [
        route.path
        for route in create_admin_app().routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api/admin/")
        and route.path not in public_paths
        and not any(
            dependency.call is get_current_admin_session
            for dependency in route.dependant.dependencies
        )
    ]

    assert unprotected_routes == []


def _app_with_password_transport(tmp_path: Path):
    key_path = tmp_path / "password.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            password_transport=PasswordTransportSettings(private_key_path=str(key_path))
        ),
    )
    return create_admin_app(bootstrap=bootstrap, runtime=runtime)


def _contract_hash(openapi: dict[str, object], prefix: str) -> str:
    all_paths = cast(dict[str, object], openapi["paths"])
    paths = {key: value for key, value in all_paths.items() if key.startswith(prefix)}
    components = cast(dict[str, object], openapi["components"])
    all_schemas = cast(dict[str, object], components["schemas"])
    names: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                names.add(ref.rsplit("/", 1)[-1])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(paths)
    pending = list(names)
    while pending:
        name = pending.pop()
        before = set(names)
        collect(all_schemas[name])
        pending.extend(names - before)
    contract = {
        "paths": paths,
        "schemas": {name: all_schemas[name] for name in sorted(names)},
    }
    payload = json.dumps(
        contract,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()
