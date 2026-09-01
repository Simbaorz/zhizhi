"""Real Admin Roles HTTP flow through SQLite, RSA, JWT, RBAC, and audit."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from gewu_core.config import BootstrapSettings
from gewu_core.http import PasswordTransportSettings, RsaPasswordTransport
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform.audit import AdminAuditLogModel
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import JwtSettings, hash_password
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminRoleModel,
    AdminRolePermissionModel,
    AdminTenantMemberModel,
    AdminTenantRoleModel,
    AdminUserModel,
    TenantModel,
)

JWT_SIGNING_KEY = "admin-roles-integration-signing-key"
ROLES_CONTRACT_SHA256 = "0cf109b8c9e75e1027752847f5ee6cf511cd41bd54af412267ba82f086075337"


def test_create_role_success(tmp_path: Path) -> None:
    with _super_role_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/roles",
            headers=headers,
            json={
                "role_code": "auditor",
                "role_name": "Auditor",
                "description": "Audit role",
                "status": "active",
            },
        )

    assert response.status_code == 200
    assert response.json()["role_code"] == "auditor"


def test_create_role_rejects_unknown_status(tmp_path: Path) -> None:
    with _super_role_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/roles",
            headers=headers,
            json={
                "role_code": "auditor",
                "role_name": "Auditor",
                "status": "enabled",
            },
        )

    assert response.status_code == 422


def test_list_roles_supports_pagination(tmp_path: Path) -> None:
    with _super_role_client(tmp_path) as (client, _, headers):
        created_roles: list[dict[str, object]] = []
        for role_code, role_name in (
            ("tenant_files", "Tenant Files"),
            ("division_files", "Division Files"),
            ("team_files", "Team Files"),
        ):
            created = client.post(
                "/api/admin/roles",
                headers=headers,
                json={"role_code": role_code, "role_name": role_name},
            )
            assert created.status_code == 200
            created_roles.append(created.json())

        response = client.get(
            "/api/admin/roles",
            headers=headers,
            params={"page": 2, "page_size": 1, "search": "files"},
        )

    assert response.status_code == 200
    assert response.json()["pagination"] == {"page": 2, "page_size": 1, "total": 3}
    expected_role = sorted(created_roles, key=lambda role: str(role["id"]))[1]
    assert response.json()["roles"][0]["role_code"] == expected_role["role_code"]


def test_delete_role_success(tmp_path: Path) -> None:
    with _super_role_client(tmp_path) as (client, _, headers):
        created = client.post(
            "/api/admin/roles",
            headers=headers,
            json={"role_code": "auditor", "role_name": "Auditor"},
        )
        assert created.status_code == 200
        role_id = created.json()["id"]
        response = client.delete(f"/api/admin/roles/{role_id}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            assert session.get(AdminRoleModel, role_id) is None
    finally:
        engine.dispose()


def test_role_permission_endpoints_validate_role_and_permission_ids(tmp_path: Path) -> None:
    with _super_role_client(tmp_path) as (client, _, headers):
        created = client.post(
            "/api/admin/roles",
            headers=headers,
            json={"role_code": "auditor", "role_name": "Auditor"},
        )
        assert created.status_code == 200
        role_id = created.json()["id"]
        permissions = client.get("/api/admin/permissions", headers=headers)
        assert permissions.status_code == 200
        permission_id = permissions.json()["permissions"][0]["id"]

        missing_list_response = client.get(
            "/api/admin/roles/missing/permissions",
            headers=headers,
        )
        missing_replace_response = client.put(
            "/api/admin/roles/missing/permissions",
            headers=headers,
            json={"permission_ids": [permission_id]},
        )
        invalid_permission_response = client.put(
            f"/api/admin/roles/{role_id}/permissions",
            headers=headers,
            json={"permission_ids": ["missing"]},
        )

    assert missing_list_response.status_code == 404
    assert missing_replace_response.status_code == 404
    assert invalid_permission_response.status_code == 422
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            bindings = list(
                session.scalars(
                    select(AdminRolePermissionModel).where(
                        AdminRolePermissionModel.role_id == role_id
                    )
                )
            )
            assert bindings == []
    finally:
        engine.dispose()


def test_admin_roles_round_trip_matches_zhizhi_behavior(tmp_path: Path) -> None:
    key_path = _write_private_key(tmp_path)
    _seed_admin_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            password_transport=PasswordTransportSettings(private_key_path=str(key_path)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        super_token = _login(client, transport, "root", "secret")
        regular_token = _login(client, transport, "operator", "secret")
        super_headers = _cookie_headers(super_token)
        regular_headers = _cookie_headers(regular_token)

        denied = client.get("/api/admin/roles", headers=regular_headers)
        assert denied.status_code == 403
        assert denied.json() == {"detail": "Super admin privileges are required."}

        permissions = client.get("/api/admin/permissions", headers=super_headers)
        assert permissions.status_code == 200
        permission_ids = {
            row["permission_code"]: row["id"] for row in permissions.json()["permissions"]
        }
        assert "org.view" in permission_ids

        created = client.post(
            "/api/admin/roles",
            headers=super_headers,
            json={
                "role_code": "ops",
                "role_name": "Operations",
                "description": "Initial",
                "status": "active",
                "is_delegable": True,
            },
        )
        assert created.status_code == 200
        role_id = created.json()["id"]
        duplicate = client.post(
            "/api/admin/roles",
            headers=super_headers,
            json={"role_code": "ops", "role_name": "Duplicate"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": "角色编码已存在。"}

        listed = client.get(
            "/api/admin/roles",
            headers=super_headers,
            params={"search": "operation", "status": "active", "page": 1, "page_size": 1},
        )
        assert listed.status_code == 200
        assert listed.json()["pagination"] == {"page": 1, "page_size": 1, "total": 1}
        assert listed.json()["roles"][0]["id"] == role_id
        assert listed.json()["roles"][0]["permission_count"] == 0

        updated = client.patch(
            f"/api/admin/roles/{role_id}",
            headers=super_headers,
            json={"role_name": "Operations 2", "status": "inactive"},
        )
        assert updated.status_code == 200
        assert updated.json()["role_name"] == "Operations 2"
        assert updated.json()["description"] == "Initial"
        assert updated.json()["status"] == "inactive"

        replaced = client.put(
            f"/api/admin/roles/{role_id}/permissions",
            headers=super_headers,
            json={
                "permission_ids": [
                    permission_ids["org.view"],
                    permission_ids["skills.view"],
                    permission_ids["org.view"],
                ]
            },
        )
        assert replaced.status_code == 200
        assert replaced.json() == {"ok": True}
        role_permissions = client.get(
            f"/api/admin/roles/{role_id}/permissions", headers=super_headers
        )
        assert role_permissions.status_code == 200
        assert [row["permission_code"] for row in role_permissions.json()["permissions"]] == [
            "org.view",
            "skills.view",
        ]

        missing = client.put(
            f"/api/admin/roles/{role_id}/permissions",
            headers=super_headers,
            json={"permission_ids": ["missing-permission"]},
        )
        assert missing.status_code == 422
        assert missing.json() == {"detail": "权限不存在：missing-permission"}
        unchanged_permissions = client.get(
            f"/api/admin/roles/{role_id}/permissions", headers=super_headers
        )
        assert unchanged_permissions.status_code == 200
        assert [row["permission_code"] for row in unchanged_permissions.json()["permissions"]] == [
            "org.view",
            "skills.view",
        ]

        _bind_role_to_tenant_member(tmp_path, role_id)

        deleted = client.delete(f"/api/admin/roles/{role_id}", headers=super_headers)
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}
        assert (
            client.get(f"/api/admin/roles/{role_id}/permissions", headers=super_headers).status_code
            == 404
        )
        missing_role_replace = client.put(
            f"/api/admin/roles/{role_id}/permissions",
            headers=super_headers,
            json={"permission_ids": ["missing-permission"]},
        )
        assert missing_role_replace.status_code == 404
        assert missing_role_replace.json() == {"detail": "角色不存在。"}

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            assert session.get(AdminRoleModel, role_id) is None
            assert session.get(AdminTenantRoleModel, "tenant-role-binding") is None
            assert session.get(AdminTenantMemberModel, "tenant-member-role") is not None
            assert session.get(TenantModel, "tenant-role") is not None
            assert (
                list(
                    session.scalars(
                        select(AdminRolePermissionModel).where(
                            AdminRolePermissionModel.role_id == role_id
                        )
                    )
                )
                == []
            )
            audit_rows = list(session.scalars(select(AdminAuditLogModel)))
    finally:
        engine.dispose()
    assert [row.action for row in audit_rows] == [
        "admin.http.post",
        "admin.http.patch",
        "admin.http.put",
        "admin.http.delete",
    ]


def test_admin_roles_openapi_matches_zhizhi_baseline() -> None:
    spec = create_admin_app().openapi()
    paths = cast(dict[str, object], spec["paths"])
    selected = {
        path: value
        for path, value in paths.items()
        if path
        in {
            "/api/admin/roles",
            "/api/admin/roles/{role_id}",
            "/api/admin/roles/{role_id}/permissions",
            "/api/admin/permissions",
        }
    }
    assert _contract_hash(spec, selected) == ROLES_CONTRACT_SHA256


@contextmanager
def _super_role_client(
    project_home: Path,
) -> Iterator[tuple[TestClient, ZhizhiAdminApiRuntime, dict[str, str]]]:
    key_path = _write_private_key(project_home)
    _seed_admin_database(project_home)
    bootstrap = BootstrapSettings(PROJECT_HOME=project_home)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            password_transport=PasswordTransportSettings(private_key_path=str(key_path)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)
    with TestClient(app) as client:
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        token = security.issue_admin_token(
            user_id="admin-super",
            username="root",
            is_super=True,
        )
        yield client, runtime, _cookie_headers(token)


def _login(
    client: TestClient,
    transport: RsaPasswordTransport,
    username: str,
    password: str,
) -> str:
    response = client.post(
        "/api/admin/auth/login",
        json={
            "username": username,
            "encrypted_password": transport.encrypt_for_transport(password),
        },
    )
    assert response.status_code == 200
    assert "token" not in response.json()
    token = client.cookies.get("zhizhi_admin_session")
    assert token
    return token


def _cookie_headers(token: str) -> dict[str, str]:
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }


def _seed_admin_database(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    ZhizhiBase.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    AdminUserModel(
                        id="admin-super",
                        username="root",
                        normalized_username="ROOT",
                        password_hash=hash_password("secret"),
                        is_super=True,
                    ),
                    AdminUserModel(
                        id="admin-regular",
                        username="operator",
                        normalized_username="OPERATOR",
                        password_hash=hash_password("secret"),
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _bind_role_to_tenant_member(project_home: Path, role_id: str) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    TenantModel(
                        id="tenant-role",
                        tenant_code="ROLE",
                        normalized_tenant_code="ROLE",
                        storage_key="ROLE",
                        tenant_name="Role Tenant",
                    ),
                    AdminTenantMemberModel(
                        id="tenant-member-role",
                        admin_user_id="admin-regular",
                        tenant_id="tenant-role",
                    ),
                    AdminTenantRoleModel(
                        id="tenant-role-binding",
                        tenant_member_id="tenant-member-role",
                        role_id=role_id,
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _write_private_key(project_home: Path) -> Path:
    path = project_home / "password.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


def _contract_hash(spec: dict[str, object], paths: dict[str, object]) -> str:
    components = cast(dict[str, object], spec["components"])
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
    payload = json.dumps(
        {
            "paths": paths,
            "schemas": {name: all_schemas[name] for name in sorted(names)},
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()
