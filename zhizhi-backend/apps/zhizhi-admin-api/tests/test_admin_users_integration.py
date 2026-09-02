"""Real Admin user management flow through SQLite, RSA, JWT, RBAC, and audit."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

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
from zhizhi_platform.iam import JwtSettings, hash_password, verify_password
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminRoleModel,
    AdminRolePermissionModel,
    AdminTenantMemberModel,
    AdminTenantRoleModel,
    AdminTenantScopeModel,
    AdminUserModel,
    OrganizationUnitModel,
    TenantModel,
)

JWT_SIGNING_KEY = "admin-users-integration-signing-key"


def test_global_admin_users_endpoint_is_removed(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, _, headers):
        response = client.get("/api/admin/users", headers=headers)

    assert response.status_code == 404


def test_list_tenant_admins_aggregates_members_in_tenant(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, headers):
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        created = client.post(
            "/api/admin/users/create-or-bind",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "username": "ops",
                "encrypted_password": transport.encrypt_for_transport("secret"),
                "display_name": "Operations",
            },
        )
        assert created.status_code == 200
        user_id = created.json()["admin_user_id"]
        member_id = created.json()["id"]
        _assign_admin_role_and_scope(
            tmp_path,
            member_id=member_id,
            role_id="role-unit-ops",
            role_code="unit_ops",
            role_name="Unit Operations",
            scope_type="organization_unit",
            scope_organization_unit_id="team-1",
        )

        response = client.get(
            "/api/admin/users/tenant-admins",
            headers=headers,
            params={"tenant_id": "tenant-1"},
        )

    assert response.status_code == 200
    users = response.json()["users"]
    target = next(user for user in users if user["id"] == user_id)
    assert target["username"] == "ops"
    assert target["tenant_id"] == "tenant-1"
    assert target["tenant_admin_status"] == "active"
    assert target["roles"][0]["role_code"] == "unit_ops"
    assert target["scopes"][0]["scope_type"] == "organization_unit"
    assert response.json()["pagination"] == {"page": 1, "page_size": 20, "total": 1}


def test_global_admin_user_create_endpoint_is_removed(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, headers):
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "root2",
                "encrypted_password": transport.encrypt_for_transport("root-pass"),
                "display_name": "Root 2",
                "status": "active",
                "is_super": True,
            },
        )

    assert response.status_code == 404


def test_create_or_bind_admin_user_only_binds_tenant_member(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, headers):
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        response = client.post(
            "/api/admin/users/create-or-bind",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "username": "OpsUser",
                "encrypted_password": transport.encrypt_for_transport("new-secret"),
                "display_name": "Ops",
                "status": "active",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["identity_action"] == "created"
    assert body["roles"] == []
    assert body["scopes"] == []
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            user = session.get(AdminUserModel, body["admin_user_id"])
            member = session.get(AdminTenantMemberModel, body["id"])
            assert user is not None
            assert member is not None
            assert user.username == "OpsUser"
            assert user.normalized_username == "OPSUSER"
            assert member.admin_user_id == user.id
            assert member.tenant_id == "tenant-1"
            assert (
                list(
                    session.scalars(
                        select(AdminTenantRoleModel).where(
                            AdminTenantRoleModel.tenant_member_id == member.id
                        )
                    )
                )
                == []
            )
            assert (
                list(
                    session.scalars(
                        select(AdminTenantScopeModel).where(
                            AdminTenantScopeModel.tenant_member_id == member.id
                        )
                    )
                )
                == []
            )
    finally:
        engine.dispose()


def test_create_or_bind_admin_user_rejects_already_bound_identity(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, headers):
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        first = client.post(
            "/api/admin/users/create-or-bind",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "username": "Ops",
                "encrypted_password": transport.encrypt_for_transport("secret"),
            },
        )
        assert first.status_code == 200
        response = client.post(
            "/api/admin/users/create-or-bind",
            headers=headers,
            json={"tenant_id": "tenant-1", "username": "ops"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "already_bound"}


def test_update_admin_user_requires_scope(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, headers):
        user_id = _create_admin(client, runtime, headers)
        response = client.patch(
            f"/api/admin/users/{user_id}",
            headers=headers,
            json={"display_name": "Changed"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Admin account scope is required."}
    assert _admin_user(tmp_path, user_id).display_name == "Operations"


def test_update_admin_user_explicitly_rejects_username(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, headers):
        user_id = _create_admin(client, runtime, headers)
        response = client.patch(
            f"/api/admin/users/{user_id}",
            headers=headers,
            json={
                "username": "Other",
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
            },
        )

    assert response.status_code == 422
    assert _admin_user(tmp_path, user_id).username == "OpsUser"


def test_update_self_admin_rejected(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, _):
        _seed_scoped_admin_and_shared_target(tmp_path)
        headers = _admin_headers(runtime, "admin-operator", "operator")
        response = client.patch(
            "/api/admin/users/admin-operator",
            headers=headers,
            json={
                "display_name": "Changed",
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Current account cannot modify its own admin permissions."}
    assert _admin_user(tmp_path, "admin-operator").display_name == ""


def test_tenant_admin_cannot_change_identity_shared_with_another_tenant(
    tmp_path: Path,
) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, _):
        _seed_scoped_admin_and_shared_target(tmp_path)
        headers = _admin_headers(runtime, "admin-operator", "operator")
        scope = {"scope_type": "tenant", "scope_tenant_id": "tenant-1"}
        identity_response = client.patch(
            "/api/admin/users/admin-shared",
            headers=headers,
            json={**scope, "display_name": "Changed"},
        )
        membership_response = client.patch(
            "/api/admin/users/admin-shared",
            headers=headers,
            json={**scope, "status": "inactive"},
        )

    assert identity_response.status_code == 403
    assert identity_response.json() == {
        "detail": "跨租户共享的管理员身份只能由超级管理员或账号本人修改。"
    }
    assert membership_response.status_code == 200
    assert _admin_user(tmp_path, "admin-shared").display_name == "Shared"
    assert _admin_member(tmp_path, "shared-member-1").status == "inactive"
    assert _admin_member(tmp_path, "shared-member-2").status == "active"


def test_reset_password_changes_login_password(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, headers):
        user_id = _create_admin(client, runtime, headers, password="old-secret")
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        reset = client.post(
            f"/api/admin/users/{user_id}/reset-password",
            headers=headers,
            json={
                "encrypted_password": transport.encrypt_for_transport("new-secret"),
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
            },
        )
        old_login = client.post(
            "/api/admin/auth/login",
            json={
                "username": "opsuser",
                "encrypted_password": transport.encrypt_for_transport("old-secret"),
            },
        )
        new_login = client.post(
            "/api/admin/auth/login",
            json={
                "username": "oPsUsEr",
                "encrypted_password": transport.encrypt_for_transport("new-secret"),
            },
        )

    assert reset.status_code == 200
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert new_login.json()["user"]["username"] == "OpsUser"
    assert _admin_user(tmp_path, user_id).token_version == 1


def test_scoped_admin_can_reset_password_for_admin_in_scope(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, _):
        _seed_scoped_admin_and_shared_target(tmp_path)
        _seed_local_scoped_target(tmp_path)
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        response = client.post(
            "/api/admin/users/admin-local/reset-password",
            headers=_admin_headers(runtime, "admin-operator", "operator"),
            json={
                "encrypted_password": transport.encrypt_for_transport("new-secret"),
                "scope_type": "organization_unit",
                "scope_tenant_id": "tenant-1",
                "scope_organization_unit_id": "team-1",
            },
        )

    assert response.status_code == 200
    assert verify_password("new-secret", _admin_user(tmp_path, "admin-local").password_hash)


def test_reset_self_admin_password_rejected(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, runtime, _):
        _seed_scoped_admin_and_shared_target(tmp_path)
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        response = client.post(
            "/api/admin/users/admin-operator/reset-password",
            headers=_admin_headers(runtime, "admin-operator", "operator"),
            json={
                "encrypted_password": transport.encrypt_for_transport("new-secret"),
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Current account cannot modify its own admin permissions."}


def test_global_user_roles_endpoint_is_removed(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, _, headers):
        response = client.put(
            "/api/admin/users/admin-super/roles",
            headers=headers,
            json={"role_ids": ["role-1", "role-2"]},
        )

    assert response.status_code == 404


def test_admin_login_rejects_plaintext_password_field(tmp_path: Path) -> None:
    with _super_admin_client(tmp_path) as (client, _, _):
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "root", "password": "secret"},
        )

    assert response.status_code == 422


def test_admin_users_round_trip_matches_zhizhi_behavior(tmp_path: Path) -> None:
    key_path = _write_private_key(tmp_path)
    _seed_database(tmp_path)
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
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        token = security.issue_admin_token(
            user_id="admin-super",
            username="root",
            is_super=True,
        )
        headers = _cookie_headers(token)

        created = client.post(
            "/api/admin/users/create-or-bind",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "username": "OpsUser",
                "encrypted_password": transport.encrypt_for_transport("initial-secret"),
                "display_name": "Operations",
                "phone": " 13800000000 ",
                "email": " OPS@EXAMPLE.COM ",
                "status": "active",
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["identity_action"] == "created"
        assert payload["roles"] == []
        assert payload["scopes"] == []
        user_id = payload["admin_user_id"]

        duplicate = client.post(
            "/api/admin/users/create-or-bind",
            headers=headers,
            json={"tenant_id": "tenant-1", "username": "opsuser"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": "already_bound"}

        listed = client.get(
            "/api/admin/users/tenant-admins",
            headers=headers,
            params={
                "tenant_id": "tenant-1",
                "search": "operations",
                "status": "active",
                "page": 1,
                "page_size": 20,
            },
        )
        assert listed.status_code == 200
        assert listed.json()["pagination"] == {"page": 1, "page_size": 20, "total": 1}
        assert listed.json()["users"][0]["id"] == user_id
        assert listed.json()["users"][0]["tenant_admin_status"] == "active"

        immutable = client.patch(
            f"/api/admin/users/{user_id}",
            headers=headers,
            json={
                "username": "Other",
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
            },
        )
        assert immutable.status_code == 422

        updated = client.patch(
            f"/api/admin/users/{user_id}",
            headers=headers,
            json={
                "display_name": "Operations 2",
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "Operations 2"
        assert updated.json()["tenant_id"] == "tenant-1"

        reset = client.post(
            f"/api/admin/users/{user_id}/reset-password",
            headers=headers,
            json={
                "encrypted_password": transport.encrypt_for_transport("new-secret"),
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
            },
        )
        assert reset.status_code == 200
        assert reset.json() == {"ok": True}

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            user = session.get(AdminUserModel, user_id)
            assert user is not None
            assert user.normalized_username == "OPSUSER"
            assert user.phone == "13800000000"
            assert user.email == "ops@example.com"
            assert user.display_name == "Operations 2"
            assert user.token_version == 1
            assert verify_password("new-secret", user.password_hash)
            member = session.scalar(
                select(AdminTenantMemberModel).where(
                    AdminTenantMemberModel.admin_user_id == user_id,
                    AdminTenantMemberModel.tenant_id == "tenant-1",
                )
            )
            assert member is not None
            audit_rows = list(session.scalars(select(AdminAuditLogModel)))
    finally:
        engine.dispose()
    assert [row.action for row in audit_rows] == [
        "admin_identity.create",
        "admin_tenant_member.bind",
        "admin.http.post",
        "admin_identity.reuse",
        "admin_identity.update",
        "admin.http.patch",
        "admin_identity.reset_password",
        "admin.http.post",
    ]


def test_admin_users_openapi_publishes_tenant_account_routes() -> None:
    spec = create_admin_app().openapi()
    paths = {path for path in spec["paths"] if path.startswith("/api/admin/users")}
    assert paths == {
        "/api/admin/users/tenant-admins",
        "/api/admin/users/create-or-bind",
        "/api/admin/users/{user_id}",
        "/api/admin/users/{user_id}/reset-password",
    }


def test_admin_user_scope_and_shared_identity_guards_match_zhizhi_behavior(
    tmp_path: Path,
) -> None:
    key_path = _write_private_key(tmp_path)
    _seed_database(tmp_path)
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
        _seed_scoped_admin_and_shared_target(tmp_path)
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-operator",
                username="operator",
                is_super=False,
            )
        )
        scope = {"scope_type": "tenant", "scope_tenant_id": "tenant-1"}

        self_update = client.patch(
            "/api/admin/users/admin-operator",
            headers=headers,
            json={**scope, "status": "inactive"},
        )
        assert self_update.status_code == 403
        assert self_update.json() == {
            "detail": "Current account cannot modify its own admin permissions."
        }

        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        self_reset = client.post(
            "/api/admin/users/admin-operator/reset-password",
            headers=headers,
            json={
                **scope,
                "encrypted_password": transport.encrypt_for_transport("replacement"),
            },
        )
        assert self_reset.status_code == 403
        assert self_reset.json() == {
            "detail": "Current account cannot modify its own admin permissions."
        }

        shared_identity_update = client.patch(
            "/api/admin/users/admin-shared",
            headers=headers,
            json={**scope, "display_name": "Changed"},
        )
        assert shared_identity_update.status_code == 403
        assert shared_identity_update.json() == {
            "detail": "跨租户共享的管理员身份只能由超级管理员或账号本人修改。"
        }

        tenant_member_update = client.patch(
            "/api/admin/users/admin-shared",
            headers=headers,
            json={**scope, "status": "inactive"},
        )
        assert tenant_member_update.status_code == 200
        assert tenant_member_update.json()["display_name"] == "Shared"
        assert tenant_member_update.json()["tenant_admin_status"] == "inactive"

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            operator = session.get(AdminUserModel, "admin-operator")
            shared = session.get(AdminUserModel, "admin-shared")
            tenant_one_member = session.get(AdminTenantMemberModel, "shared-member-1")
            tenant_two_member = session.get(AdminTenantMemberModel, "shared-member-2")
            assert operator is not None and operator.status == "active"
            assert verify_password("secret", operator.password_hash)
            assert shared is not None and shared.display_name == "Shared"
            assert tenant_one_member is not None and tenant_one_member.status == "inactive"
            assert tenant_two_member is not None and tenant_two_member.status == "active"
    finally:
        engine.dispose()


@contextmanager
def _super_admin_client(
    project_home: Path,
) -> Iterator[tuple[TestClient, ZhizhiAdminApiRuntime, dict[str, str]]]:
    key_path = _write_private_key(project_home)
    _seed_database(project_home)
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
        yield client, runtime, _admin_headers(runtime, "admin-super", "root", is_super=True)


def _admin_headers(
    runtime: ZhizhiAdminApiRuntime,
    user_id: str,
    username: str,
    *,
    is_super: bool = False,
) -> dict[str, str]:
    security = runtime._iam.identity_security if runtime._iam is not None else None
    assert security is not None
    token = security.issue_admin_token(
        user_id=user_id,
        username=username,
        is_super=is_super,
    )
    return _cookie_headers(token)


def _cookie_headers(token: str) -> dict[str, str]:
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }


def _create_admin(
    client: TestClient,
    runtime: ZhizhiAdminApiRuntime,
    headers: dict[str, str],
    *,
    password: str = "secret",
) -> str:
    transport = runtime.password_transport
    assert isinstance(transport, RsaPasswordTransport)
    response = client.post(
        "/api/admin/users/create-or-bind",
        headers=headers,
        json={
            "tenant_id": "tenant-1",
            "username": "OpsUser",
            "encrypted_password": transport.encrypt_for_transport(password),
            "display_name": "Operations",
        },
    )
    assert response.status_code == 200
    return str(response.json()["admin_user_id"])


def _admin_user(project_home: Path, user_id: str) -> AdminUserModel:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            user = session.get(AdminUserModel, user_id)
            assert user is not None
            session.expunge(user)
            return user
    finally:
        engine.dispose()


def _admin_member(project_home: Path, member_id: str) -> AdminTenantMemberModel:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            member = session.get(AdminTenantMemberModel, member_id)
            assert member is not None
            session.expunge(member)
            return member
    finally:
        engine.dispose()


def _assign_admin_role_and_scope(
    project_home: Path,
    *,
    member_id: str,
    role_id: str,
    role_code: str,
    role_name: str,
    scope_type: str,
    scope_organization_unit_id: str = "",
) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            member = session.get(AdminTenantMemberModel, member_id)
            assert member is not None
            member.scope_mode = scope_type
            session.add_all(
                [
                    AdminRoleModel(
                        id=role_id,
                        role_code=role_code,
                        role_name=role_name,
                    ),
                    AdminTenantRoleModel(
                        id=f"{member_id}-role",
                        tenant_member_id=member_id,
                        role_id=role_id,
                    ),
                    AdminTenantScopeModel(
                        id=f"{member_id}-scope",
                        tenant_member_id=member_id,
                        scope_type=scope_type,
                        scope_organization_unit_id=scope_organization_unit_id,
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_local_scoped_target(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    OrganizationUnitModel(
                        id="team-1",
                        tenant_id="tenant-1",
                        external_key="TEAM",
                        normalized_external_key="TEAM",
                        storage_key="team-1",
                        name="Team 1",
                        unit_type="team",
                    ),
                    AdminUserModel(
                        id="admin-local",
                        username="local",
                        normalized_username="LOCAL",
                        password_hash=hash_password("old-secret"),
                    ),
                    AdminTenantMemberModel(
                        id="local-member",
                        admin_user_id="admin-local",
                        tenant_id="tenant-1",
                        scope_mode="organization_unit",
                    ),
                    AdminTenantScopeModel(
                        id="local-member-scope",
                        tenant_member_id="local-member",
                        scope_type="organization_unit",
                        scope_organization_unit_id="team-1",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_database(project_home: Path) -> None:
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
                    TenantModel(
                        id="tenant-1",
                        tenant_code="T1",
                        normalized_tenant_code="T1",
                        storage_key="T1",
                        tenant_name="Tenant 1",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_scoped_admin_and_shared_target(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            permissions = {
                row.permission_code: row
                for row in session.scalars(
                    select(AdminPermissionModel).where(
                        AdminPermissionModel.permission_code.in_(
                            ("admins.update", "admins.reset_password")
                        )
                    )
                )
            }
            assert set(permissions) == {"admins.update", "admins.reset_password"}
            session.add_all(
                [
                    TenantModel(
                        id="tenant-2",
                        tenant_code="T2",
                        normalized_tenant_code="T2",
                        storage_key="T2",
                        tenant_name="Tenant 2",
                    ),
                    AdminUserModel(
                        id="admin-operator",
                        username="operator",
                        normalized_username="OPERATOR",
                        password_hash=hash_password("secret"),
                    ),
                    AdminUserModel(
                        id="admin-shared",
                        username="shared",
                        normalized_username="SHARED",
                        password_hash=hash_password("secret"),
                        display_name="Shared",
                    ),
                    AdminRoleModel(
                        id="role-account-manager",
                        role_code="account_manager_test",
                        role_name="Account Manager",
                    ),
                    AdminRolePermissionModel(
                        id="role-account-manager-update",
                        role_id="role-account-manager",
                        permission_id=permissions["admins.update"].id,
                    ),
                    AdminRolePermissionModel(
                        id="role-account-manager-reset",
                        role_id="role-account-manager",
                        permission_id=permissions["admins.reset_password"].id,
                    ),
                    AdminTenantMemberModel(
                        id="operator-member",
                        admin_user_id="admin-operator",
                        tenant_id="tenant-1",
                        scope_mode="tenant",
                    ),
                    AdminTenantRoleModel(
                        id="operator-member-role",
                        tenant_member_id="operator-member",
                        role_id="role-account-manager",
                    ),
                    AdminTenantScopeModel(
                        id="operator-member-scope",
                        tenant_member_id="operator-member",
                        scope_type="tenant",
                    ),
                    AdminTenantMemberModel(
                        id="shared-member-1",
                        admin_user_id="admin-shared",
                        tenant_id="tenant-1",
                        scope_mode="organization_unit",
                    ),
                    AdminTenantScopeModel(
                        id="shared-member-1-scope",
                        tenant_member_id="shared-member-1",
                        scope_type="organization_unit",
                        scope_organization_unit_id="team-1",
                    ),
                    AdminTenantMemberModel(
                        id="shared-member-2",
                        admin_user_id="admin-shared",
                        tenant_id="tenant-2",
                        scope_mode="tenant",
                    ),
                    AdminTenantScopeModel(
                        id="shared-member-2-scope",
                        tenant_member_id="shared-member-2",
                        scope_type="tenant",
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
