"""Real Admin tenant-member HTTP flow through SQLite, JWT, RBAC, and audit."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from gewu_core.config import BootstrapSettings
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform.audit import AdminAuditLogModel
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import JwtSettings, hash_password
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

JWT_SIGNING_KEY = "admin-tenant-members-integration-key"


def test_tenant_member_authorization_accepts_organization_unit_scope_for_role(
    tmp_path: Path,
) -> None:
    with _tenant_member_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **_target_authorization(),
                "scope_mode": "organization_unit",
                "scopes": [_organization_unit_scope("team-1")],
            },
        )

    assert response.status_code == 200
    assert response.json()["scope_mode"] == "organization_unit"
    assert response.json()["roles"][0]["role_id"] == "role-operator"


def test_tenant_member_authorization_rejects_unknown_status(tmp_path: Path) -> None:
    with _tenant_member_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **_target_authorization(),
                "scopes": [_tenant_scope()],
                "status": "enabled",
            },
        )

    assert response.status_code == 422


def test_tenant_member_authorization_rejects_multiple_organization_unit_scopes(
    tmp_path: Path,
) -> None:
    with _tenant_member_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **_target_authorization(),
                "scopes": [
                    _organization_unit_scope("team-1"),
                    _organization_unit_scope("team-2"),
                ],
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "At most one organization-unit scope is allowed."}
    _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)


def test_tenant_member_authorization_rejects_team_scopes(tmp_path: Path) -> None:
    with _tenant_member_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **_target_authorization(),
                "scope_mode": "team",
                "scopes": [_team_scope("team-1"), _team_scope("team-2")],
            },
        )

    assert response.status_code == 422
    _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)


def test_tenant_member_authorization_rejects_region_and_team_scopes(tmp_path: Path) -> None:
    with _tenant_member_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **_target_authorization(),
                "scopes": [
                    _organization_unit_scope("team-1"),
                    _team_scope("team-1"),
                    _team_scope("team-2"),
                ],
            },
        )

    assert response.status_code == 422
    _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)


def test_tenant_member_authorization_rejects_tenant_scope_with_other_scopes(
    tmp_path: Path,
) -> None:
    with _tenant_member_client(tmp_path) as (client, _, headers):
        response = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **_target_authorization(),
                "scopes": [_tenant_scope(), _team_scope("team-1")],
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "literal_error"
    _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)


def test_tenant_member_authorization_rejects_role_permissions_outside_operator_scope(
    tmp_path: Path,
) -> None:
    with _tenant_member_client(tmp_path) as (client, runtime, _):
        _seed_regular_authorizer(tmp_path)
        response = client.post(
            "/api/admin/tenant-members",
            headers=_regular_headers(runtime),
            json={
                **_target_authorization(role_id="role-danger"),
                "scopes": [_organization_unit_scope("division-1")],
            },
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Current account cannot assign roles with permissions it does not have."
    }
    _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)


def test_tenant_member_authorization_allows_role_permissions_within_operator_scope(
    tmp_path: Path,
) -> None:
    with _tenant_member_client(tmp_path) as (client, runtime, _):
        _seed_regular_authorizer(tmp_path)
        response = client.post(
            "/api/admin/tenant-members",
            headers=_regular_headers(runtime),
            json={
                **_target_authorization(role_id="role-skill-viewer"),
                "scopes": [_organization_unit_scope("division-1")],
            },
        )

    assert response.status_code == 200
    assert response.json()["roles"][0]["role_id"] == "role-skill-viewer"
    assert response.json()["scopes"][0]["scope_type"] == "organization_unit"
    _assert_member_authorization_rows(tmp_path, roles=1, scopes=1)


def test_tenant_member_authorization_rejects_self_operation(tmp_path: Path) -> None:
    with _tenant_member_client(tmp_path) as (client, runtime, _):
        _seed_regular_authorizer(tmp_path)
        response = client.post(
            "/api/admin/tenant-members",
            headers=_regular_headers(runtime),
            json={
                "tenant_id": "tenant-1",
                "admin_user_id": "admin-authorizer",
                "role_ids": ["role-skill-viewer"],
                "scopes": [_organization_unit_scope("division-1")],
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Current account cannot modify its own admin permissions."}


def test_tenant_member_authorization_rejects_peer_admin_operation(tmp_path: Path) -> None:
    with _tenant_member_client(tmp_path) as (client, runtime, _):
        _seed_regular_authorizer(tmp_path)
        _seed_existing_member_authorization(tmp_path)
        response = client.post(
            "/api/admin/tenant-members",
            headers=_regular_headers(runtime),
            json={
                **_target_authorization(role_id="role-skill-viewer"),
                "scopes": [_tenant_scope()],
            },
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Current account can only manage subordinate admin accounts."
    }
    _assert_member_authorization_rows(tmp_path, roles=1, scopes=1)


def _assert_admin_tenant_member_round_trip_matches_zhizhi_behavior(
    tmp_path: Path,
) -> None:
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        super_token = security.issue_admin_token(
            user_id="admin-super",
            username="root",
            is_super=True,
        )
        regular_token = security.issue_admin_token(
            user_id="admin-target",
            username="target",
            is_super=False,
        )
        super_headers = _cookie_headers(super_token)
        regular_headers = _cookie_headers(regular_token)

        denied = client.get(
            "/api/admin/tenant-members/assignable-roles",
            headers=regular_headers,
        )
        assert denied.status_code == 403
        assert denied.json() == {"detail": "Missing permission: admins.assign_role"}

        assignable = client.get(
            "/api/admin/tenant-members/assignable-roles",
            headers=super_headers,
        )
        assert assignable.status_code == 200
        role_ids = {role["role_code"]: role["id"] for role in assignable.json()["roles"]}
        assert role_ids["operator"] == "role-operator"

        replaced = client.post(
            "/api/admin/tenant-members",
            headers=super_headers,
            json={
                "tenant_id": "tenant-1",
                "admin_user_id": "admin-target",
                "role_ids": ["role-operator", "role-operator"],
                "scope_mode": "ignored-by-policy",
                "scopes": [],
                "status": "active",
            },
        )
        assert replaced.status_code == 200
        assert replaced.json()["scope_mode"] == "tenant"
        assert [role["role_id"] for role in replaced.json()["roles"]] == ["role-operator"]
        assert replaced.json()["scopes"][0]["scope_type"] == "tenant"

        missing_role = client.post(
            "/api/admin/tenant-members",
            headers=super_headers,
            json={
                "tenant_id": "tenant-1",
                "admin_user_id": "admin-target",
                "role_ids": ["missing-role"],
                "scopes": [],
            },
        )
        assert missing_role.status_code == 404
        assert missing_role.json() == {"detail": "Role does not exist or is inactive."}

        deactivated = client.delete(
            "/api/admin/tenant-members/member-target",
            headers=super_headers,
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["status"] == "inactive"

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            member = session.get(AdminTenantMemberModel, "member-target")
            assert member is not None and member.status == "inactive"
            audit_rows = list(session.scalars(select(AdminAuditLogModel)))
    finally:
        engine.dispose()
    assert [row.action for row in audit_rows] == [
        "admin_tenant_member.authorize",
        "admin.http.post",
        "admin_tenant_member.deactivate",
        "admin.http.delete",
    ]


def test_list_assignable_roles_returns_roles(tmp_path: Path) -> None:
    _assert_admin_tenant_member_round_trip_matches_zhizhi_behavior(tmp_path)


def test_admin_tenant_members_openapi_publishes_authorization_routes() -> None:
    spec = create_admin_app().openapi()
    paths = {path for path in spec["paths"] if path.startswith("/api/admin/tenant-members")}
    assert paths == {
        "/api/admin/tenant-members",
        "/api/admin/tenant-members/{member_id}",
        "/api/admin/tenant-members/assignable-roles",
    }


def test_admin_tenant_member_scope_combinations_match_zhizhi_behavior(
    tmp_path: Path,
) -> None:
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-super",
                username="root",
                is_super=True,
            )
        )
        common = {
            "tenant_id": "tenant-1",
            "admin_user_id": "admin-target",
            "role_ids": ["role-operator"],
        }

        multiple_units = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **common,
                "scopes": [
                    {
                        "scope_type": "organization_unit",
                        "scope_tenant_id": "tenant-1",
                        "scope_organization_unit_id": "team-1",
                    },
                    {
                        "scope_type": "organization_unit",
                        "scope_tenant_id": "tenant-1",
                        "scope_organization_unit_id": "team-2",
                    },
                ],
            },
        )
        assert multiple_units.status_code == 422
        assert multiple_units.json() == {
            "detail": "At most one organization-unit scope is allowed."
        }

        tenant_and_team = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **common,
                "scopes": [
                    {"scope_type": "tenant", "scope_tenant_id": "tenant-1"},
                    {
                        "scope_type": "team",
                        "scope_tenant_id": "tenant-1",
                        "scope_team_id": "team-1",
                    },
                ],
            },
        )
        assert tenant_and_team.status_code == 422
        assert tenant_and_team.json()["detail"][0]["type"] == "literal_error"

        _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)

        replaced = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                **common,
                "scope_mode": "ignored-by-policy",
                "scopes": [
                    {
                        "scope_type": "organization_unit",
                        "scope_tenant_id": "tenant-1",
                        "scope_organization_unit_id": "team-1",
                    },
                ],
            },
        )
        assert replaced.status_code == 200
        assert replaced.json()["scope_mode"] == "organization_unit"
        assert [role["role_id"] for role in replaced.json()["roles"]] == ["role-operator"]
        assert {
            (
                scope["scope_type"],
                scope["scope_organization_unit_id"],
            )
            for scope in replaced.json()["scopes"]
        } == {
            ("organization_unit", "team-1"),
        }

    _assert_member_authorization_rows(tmp_path, roles=1, scopes=1)


def test_regular_admin_cannot_delegate_permissions_outside_own_scope(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        _seed_regular_authorizer(tmp_path)
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-authorizer",
                username="authorizer",
                is_super=False,
            )
        )
        scope = {
            "scope_type": "organization_unit",
            "scope_tenant_id": "tenant-1",
            "scope_organization_unit_id": "division-1",
        }

        assignable = client.get(
            "/api/admin/tenant-members/assignable-roles",
            headers=headers,
        )
        assert assignable.status_code == 200
        assignable_ids = {role["id"] for role in assignable.json()["roles"]}
        assert "role-danger" in assignable_ids
        assert "role-nondelegable" not in assignable_ids

        self_operation = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "admin_user_id": "admin-authorizer",
                "role_ids": ["role-skill-viewer"],
                "scopes": [scope],
            },
        )
        assert self_operation.status_code == 403
        assert self_operation.json() == {
            "detail": "Current account cannot modify its own admin permissions."
        }
        _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)

        not_delegable = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "admin_user_id": "admin-target",
                "role_ids": ["role-nondelegable"],
                "scopes": [scope],
            },
        )
        assert not_delegable.status_code == 403
        assert not_delegable.json() == {"detail": "Current account cannot assign this role."}
        _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)

        forbidden = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "admin_user_id": "admin-target",
                "role_ids": ["role-danger"],
                "scopes": [scope],
            },
        )
        assert forbidden.status_code == 403
        assert forbidden.json() == {
            "detail": "Current account cannot assign roles with permissions it does not have."
        }
        _assert_member_authorization_rows(tmp_path, roles=0, scopes=0)

        allowed = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "admin_user_id": "admin-target",
                "role_ids": ["role-skill-viewer"],
                "scopes": [scope],
            },
        )
        assert allowed.status_code == 200
        assert allowed.json()["scope_mode"] == "organization_unit"
        assert [role["role_id"] for role in allowed.json()["roles"]] == ["role-skill-viewer"]
        assert allowed.json()["scopes"][0]["scope_type"] == "organization_unit"

    _assert_member_authorization_rows(tmp_path, roles=1, scopes=1)


def test_tenant_member_failed_replacement_preserves_authorization_and_error_priority(
    tmp_path: Path,
) -> None:
    _seed_database(tmp_path)
    _seed_existing_member_authorization(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-super",
                username="root",
                is_super=True,
            )
        )
        common = {
            "tenant_id": "tenant-1",
            "role_ids": ["missing-role"],
            "scopes": [],
            "status": "inactive",
        }

        missing_user = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={**common, "admin_user_id": "missing-user"},
        )
        assert missing_user.status_code == 404
        assert missing_user.json() == {"detail": "Admin user does not exist."}

        missing_member = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={**common, "admin_user_id": "admin-unbound"},
        )
        assert missing_member.status_code == 404
        assert missing_member.json() == {"detail": "Admin tenant member does not exist."}

        missing_role = client.post(
            "/api/admin/tenant-members",
            headers=headers,
            json={**common, "admin_user_id": "admin-target"},
        )
        assert missing_role.status_code == 404
        assert missing_role.json() == {"detail": "Role does not exist or is inactive."}

        missing_deactivation = client.delete(
            "/api/admin/tenant-members/missing-member",
            headers=headers,
        )
        assert missing_deactivation.status_code == 404
        assert missing_deactivation.json() == {"detail": "Admin tenant member does not exist."}

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            member = session.get(AdminTenantMemberModel, "member-target")
            assert member is not None
            assert member.status == "active"
            assert member.scope_mode == "tenant"
            roles = list(
                session.scalars(
                    select(AdminTenantRoleModel).where(
                        AdminTenantRoleModel.tenant_member_id == "member-target"
                    )
                )
            )
            scopes = list(
                session.scalars(
                    select(AdminTenantScopeModel).where(
                        AdminTenantScopeModel.tenant_member_id == "member-target"
                    )
                )
            )
            audit_rows = list(session.scalars(select(AdminAuditLogModel)))
    finally:
        engine.dispose()
    assert [role.role_id for role in roles] == ["role-operator"]
    assert len(scopes) == 1
    assert scopes[0].scope_type == "tenant"
    assert audit_rows == []


@contextmanager
def _tenant_member_client(
    project_home: Path,
) -> Iterator[tuple[TestClient, ZhizhiAdminApiRuntime, dict[str, str]]]:
    _seed_database(project_home)
    bootstrap = BootstrapSettings(PROJECT_HOME=project_home)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
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


def _regular_headers(runtime: ZhizhiAdminApiRuntime) -> dict[str, str]:
    security = runtime._iam.identity_security if runtime._iam is not None else None
    assert security is not None
    token = security.issue_admin_token(
        user_id="admin-authorizer",
        username="authorizer",
        is_super=False,
    )
    return _cookie_headers(token)


def _cookie_headers(token: str) -> dict[str, str]:
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }


def _target_authorization(*, role_id: str = "role-operator") -> dict[str, object]:
    return {
        "tenant_id": "tenant-1",
        "admin_user_id": "admin-target",
        "role_ids": [role_id],
    }


def _tenant_scope() -> dict[str, str]:
    return {"scope_type": "tenant", "scope_tenant_id": "tenant-1"}


def _organization_unit_scope(organization_unit_id: str) -> dict[str, str]:
    return {
        "scope_type": "organization_unit",
        "scope_tenant_id": "tenant-1",
        "scope_organization_unit_id": organization_unit_id,
    }


def _team_scope(team_id: str) -> dict[str, str]:
    return {
        "scope_type": "team",
        "scope_tenant_id": "tenant-1",
        "scope_team_id": team_id,
    }


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
                    AdminUserModel(
                        id="admin-target",
                        username="target",
                        normalized_username="TARGET",
                        password_hash=hash_password("secret"),
                    ),
                    AdminUserModel(
                        id="admin-unbound",
                        username="unbound",
                        normalized_username="UNBOUND",
                        password_hash=hash_password("secret"),
                    ),
                    TenantModel(
                        id="tenant-1",
                        tenant_code="T1",
                        normalized_tenant_code="T1",
                        storage_key="T1",
                        tenant_name="Tenant 1",
                    ),
                    OrganizationUnitModel(
                        id="division-1",
                        tenant_id="tenant-1",
                        external_key="DIVISION",
                        normalized_external_key="DIVISION",
                        storage_key="division-1",
                        name="Division 1",
                        unit_type="division",
                    ),
                    OrganizationUnitModel(
                        id="team-1",
                        tenant_id="tenant-1",
                        parent_id="division-1",
                        external_key="TEAM1",
                        normalized_external_key="TEAM1",
                        storage_key="team-1",
                        name="Team 1",
                        unit_type="team",
                    ),
                    OrganizationUnitModel(
                        id="team-2",
                        tenant_id="tenant-1",
                        parent_id="division-1",
                        external_key="TEAM2",
                        normalized_external_key="TEAM2",
                        storage_key="team-2",
                        name="Team 2",
                        unit_type="team",
                    ),
                    AdminRoleModel(
                        id="role-operator",
                        role_code="operator",
                        role_name="Operator",
                    ),
                    AdminTenantMemberModel(
                        id="member-target",
                        admin_user_id="admin-target",
                        tenant_id="tenant-1",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_existing_member_authorization(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    AdminTenantRoleModel(
                        id="member-target-role",
                        tenant_member_id="member-target",
                        role_id="role-operator",
                    ),
                    AdminTenantScopeModel(
                        id="member-target-scope",
                        tenant_member_id="member-target",
                        scope_type="tenant",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_regular_authorizer(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            permissions = {
                row.permission_code: row
                for row in session.scalars(
                    select(AdminPermissionModel).where(
                        AdminPermissionModel.permission_code.in_(
                            ("admins.assign_role", "skills.view", "skills.edit")
                        )
                    )
                )
            }
            assert set(permissions) == {
                "admins.assign_role",
                "skills.view",
                "skills.edit",
            }
            session.add_all(
                [
                    AdminUserModel(
                        id="admin-authorizer",
                        username="authorizer",
                        normalized_username="AUTHORIZER",
                        password_hash=hash_password("secret"),
                    ),
                    AdminRoleModel(
                        id="role-authorizer",
                        role_code="authorizer_test",
                        role_name="Authorizer",
                    ),
                    AdminRoleModel(
                        id="role-skill-viewer",
                        role_code="skill_viewer_test",
                        role_name="Skill Viewer",
                        is_delegable=True,
                    ),
                    AdminRoleModel(
                        id="role-danger",
                        role_code="danger_test",
                        role_name="Danger",
                        is_delegable=True,
                    ),
                    AdminRoleModel(
                        id="role-nondelegable",
                        role_code="nondelegable_test",
                        role_name="Non-delegable",
                        is_delegable=False,
                    ),
                    AdminRolePermissionModel(
                        id="role-authorizer-assign",
                        role_id="role-authorizer",
                        permission_id=permissions["admins.assign_role"].id,
                    ),
                    AdminRolePermissionModel(
                        id="role-authorizer-view",
                        role_id="role-authorizer",
                        permission_id=permissions["skills.view"].id,
                    ),
                    AdminRolePermissionModel(
                        id="role-skill-viewer-view",
                        role_id="role-skill-viewer",
                        permission_id=permissions["skills.view"].id,
                    ),
                    AdminRolePermissionModel(
                        id="role-danger-delete",
                        role_id="role-danger",
                        permission_id=permissions["skills.edit"].id,
                    ),
                    AdminTenantMemberModel(
                        id="member-authorizer",
                        admin_user_id="admin-authorizer",
                        tenant_id="tenant-1",
                        scope_mode="tenant",
                    ),
                    AdminTenantRoleModel(
                        id="member-authorizer-role",
                        tenant_member_id="member-authorizer",
                        role_id="role-authorizer",
                    ),
                    AdminTenantScopeModel(
                        id="member-authorizer-scope",
                        tenant_member_id="member-authorizer",
                        scope_type="tenant",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _assert_member_authorization_rows(
    project_home: Path,
    *,
    roles: int,
    scopes: int,
) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            role_rows = list(
                session.scalars(
                    select(AdminTenantRoleModel).where(
                        AdminTenantRoleModel.tenant_member_id == "member-target"
                    )
                )
            )
            scope_rows = list(
                session.scalars(
                    select(AdminTenantScopeModel).where(
                        AdminTenantScopeModel.tenant_member_id == "member-target"
                    )
                )
            )
            assert len(role_rows) == roles
            assert len(scope_rows) == scopes
    finally:
        engine.dispose()
