"""Real Admin scope-catalog flow through SQLite, JWT, RBAC, and organization rows."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from gewu_core.config import BootstrapSettings
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
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

JWT_SIGNING_KEY = "scope-catalog-integration-signing-key"


def _assert_scope_catalog_filters_real_organization_rows_by_admin_grants(tmp_path: Path) -> None:
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
        super_headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-super",
                username="root",
                is_super=True,
            )
        )
        regular_headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-regular",
                username="operator",
                is_super=False,
            )
        )
        viewer_headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-viewer",
                username="viewer",
                is_super=False,
            )
        )
        unknown_headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-unknown",
                username="unknown",
                is_super=False,
            )
        )

        all_scopes = client.get("/api/admin/scope-catalog", headers=super_headers)
        assert all_scopes.status_code == 200
        assert [row["scope"]["scope_type"] for row in all_scopes.json()["scopes"]] == [
            "tenant",
            "organization_unit",
            "organization_unit",
            "tenant",
        ]

        visible = client.get("/api/admin/scope-catalog", headers=regular_headers)
        assert visible.status_code == 200
        visible_rows = visible.json()["scopes"]
        assert {row["scope"]["scope_tenant_id"] for row in visible_rows} == {"tenant-1"}
        assert {row["scope"]["scope_type"] for row in visible_rows} == {
            "tenant",
            "organization_unit",
        }

        alternative_viewer = client.get(
            "/api/admin/scope-catalog",
            headers=viewer_headers,
        )
        assert alternative_viewer.status_code == 200
        assert {row["scope"]["scope_tenant_id"] for row in alternative_viewer.json()["scopes"]} == {
            "tenant-1"
        }

        rejected = client.get(
            "/api/admin/scope-catalog",
            headers=unknown_headers,
        )
        assert rejected.status_code == 403


def test_scope_catalog_filters_to_session_tenant_members_for_normal_admin(
    tmp_path: Path,
) -> None:
    _assert_scope_catalog_filters_real_organization_rows_by_admin_grants(tmp_path)


def test_scope_catalog_accepts_skill_or_scene_viewer(tmp_path: Path) -> None:
    _assert_scope_catalog_filters_real_organization_rows_by_admin_grants(tmp_path)


def test_scope_catalog_rejects_user_without_scope_consuming_permissions(
    tmp_path: Path,
) -> None:
    _assert_scope_catalog_filters_real_organization_rows_by_admin_grants(tmp_path)


def test_scope_catalog_openapi_publishes_the_catalog_route() -> None:
    spec = create_admin_app().openapi()
    operation = spec["paths"]["/api/admin/scope-catalog"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]


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
                        id="admin-regular",
                        username="operator",
                        normalized_username="OPERATOR",
                        password_hash=hash_password("secret"),
                    ),
                    AdminUserModel(
                        id="admin-viewer",
                        username="viewer",
                        normalized_username="VIEWER",
                        password_hash=hash_password("secret"),
                    ),
                    AdminUserModel(
                        id="admin-unknown",
                        username="unknown",
                        normalized_username="UNKNOWN",
                        password_hash=hash_password("secret"),
                    ),
                    AdminPermissionModel(
                        id="permission-admins-view",
                        permission_code="admins.view",
                        permission_name="View administrators",
                    ),
                    AdminPermissionModel(
                        id="permission-skills-view",
                        permission_code="skills.view",
                        permission_name="View skills",
                    ),
                    AdminPermissionModel(
                        id="permission-scenes-view",
                        permission_code="scenes.view",
                        permission_name="View scenes",
                    ),
                    AdminPermissionModel(
                        id="permission-unknown-view",
                        permission_code="unknown.view",
                        permission_name="View unknown",
                    ),
                    AdminRoleModel(
                        id="role-operator",
                        role_code="operator",
                        role_name="Operator",
                    ),
                    AdminRoleModel(
                        id="role-viewer",
                        role_code="viewer",
                        role_name="Viewer",
                    ),
                    AdminRoleModel(
                        id="role-unknown",
                        role_code="unknown",
                        role_name="Unknown",
                    ),
                    AdminRolePermissionModel(
                        id="role-permission-operator",
                        role_id="role-operator",
                        permission_id="permission-admins-view",
                    ),
                    AdminRolePermissionModel(
                        id="role-permission-viewer-skills",
                        role_id="role-viewer",
                        permission_id="permission-skills-view",
                    ),
                    AdminRolePermissionModel(
                        id="role-permission-viewer-scenes",
                        role_id="role-viewer",
                        permission_id="permission-scenes-view",
                    ),
                    AdminRolePermissionModel(
                        id="role-permission-unknown",
                        role_id="role-unknown",
                        permission_id="permission-unknown-view",
                    ),
                    AdminTenantMemberModel(
                        id="member-regular",
                        admin_user_id="admin-regular",
                        tenant_id="tenant-1",
                    ),
                    AdminTenantRoleModel(
                        id="member-role-regular",
                        tenant_member_id="member-regular",
                        role_id="role-operator",
                    ),
                    AdminTenantScopeModel(
                        id="member-scope-regular",
                        tenant_member_id="member-regular",
                        scope_type="tenant",
                    ),
                    AdminTenantMemberModel(
                        id="member-viewer",
                        admin_user_id="admin-viewer",
                        tenant_id="tenant-1",
                    ),
                    AdminTenantRoleModel(
                        id="member-role-viewer",
                        tenant_member_id="member-viewer",
                        role_id="role-viewer",
                    ),
                    AdminTenantScopeModel(
                        id="member-scope-viewer",
                        tenant_member_id="member-viewer",
                        scope_type="tenant",
                    ),
                    AdminTenantMemberModel(
                        id="member-unknown",
                        admin_user_id="admin-unknown",
                        tenant_id="tenant-1",
                    ),
                    AdminTenantRoleModel(
                        id="member-role-unknown",
                        tenant_member_id="member-unknown",
                        role_id="role-unknown",
                    ),
                    AdminTenantScopeModel(
                        id="member-scope-unknown",
                        tenant_member_id="member-unknown",
                        scope_type="tenant",
                    ),
                    TenantModel(
                        id="tenant-1",
                        tenant_code="T1",
                        normalized_tenant_code="T1",
                        storage_key="tenant-1",
                        tenant_name="Tenant 1",
                    ),
                    TenantModel(
                        id="tenant-2",
                        tenant_code="T2",
                        normalized_tenant_code="T2",
                        storage_key="tenant-2",
                        tenant_name="Tenant 2",
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
                        external_key="TEAM",
                        normalized_external_key="TEAM",
                        storage_key="team-1",
                        name="Team 1",
                        unit_type="team",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _cookie_headers(token: str) -> dict[str, str]:
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }
