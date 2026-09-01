"""Real Admin Data Source flow through SQLite, JWT, hierarchy, and audit."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from gewu_core import JsonSecretCipher, StorageEncryptionSettings
from gewu_core.config import BootstrapSettings
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform.audit import AdminAuditLogModel
from zhizhi_platform.data_source.adapters.mysql.models import (
    DataSourceSourceBindingModel,
    DataSourceSourceEntitlementModel,
    DataSourceSourceModel,
)
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import JwtSettings
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminUserModel,
    OrganizationUnitModel,
    TenantModel,
)

JWT_SIGNING_KEY = "b" * 32
CREDENTIAL_KEY = "d" * 32


def _assert_data_source_admin_round_trip_matches_zhizhi_behavior(
    tmp_path: Path,
) -> None:
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            storage_encryption=StorageEncryptionSettings(key=CREDENTIAL_KEY),
        ),
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
        created_response = client.post(
            "/api/admin/data-sources/sources",
            headers=headers,
            json={
                "source_key": "main",
                "display_name": "Main Data",
                "status": "active",
                "api_url": "http://gateway.example/query",
                "app_id": "app",
                "app_key": "key",
                "app_secret": "secret",
                "default_database_key": "db",
                "exec_sources_code": "SQL_DEV",
            },
        )
        assert created_response.status_code == 200
        created = created_response.json()
        source_id = created["id"]
        assert created["source_key"] == "MAIN"
        assert created["has_credentials"] is True
        assert created["credential_fields"] == ["app_key", "app_secret"]
        assert "credentials_ciphertext" not in created
        assert created.get("app_key") is None
        assert created.get("app_secret") is None

        patched = client.patch(
            f"/api/admin/data-sources/sources/{source_id}",
            headers=headers,
            json={"app_key": "new-key"},
        )
        assert patched.status_code == 200
        assert patched.json()["credential_fields"] == ["app_key", "app_secret"]

        sources = client.get(
            "/api/admin/data-sources/sources",
            headers=headers,
            params={"search": "Main Data", "page_size": 1},
        )
        assert sources.status_code == 200
        assert sources.json()["pagination"] == {"page": 1, "page_size": 1, "total": 1}
        assert [row["id"] for row in sources.json()["sources"]] == [source_id]
        assert "new-key" not in str(sources.json())
        listed_source = sources.json()["sources"][0]
        assert "app_key" not in listed_source
        assert "app_secret" not in listed_source
        assert "credentials_ciphertext" not in listed_source

        tenant_entitlement = client.post(
            "/api/admin/data-sources/entitlements",
            headers=headers,
            json={
                "tenant_id": "T1",
                "scope_type": "tenant",
                "data_source_ids": [source_id],
            },
        )
        assert tenant_entitlement.status_code == 200
        tenant_entitlement_id = tenant_entitlement.json()["entitlements"][0]["id"]

        division_entitlement = client.post(
            "/api/admin/data-sources/entitlements",
            headers=headers,
            json={
                "tenant_id": "T1",
                "scope_type": "organization_unit",
                "organization_unit_id": "division-1",
                "data_source_ids": [source_id],
            },
        )
        assert division_entitlement.status_code == 200

        team_entitlement = client.post(
            "/api/admin/data-sources/entitlements",
            headers=headers,
            json={
                "tenant_id": "T1",
                "scope_type": "organization_unit",
                "organization_unit_id": "team-1",
                "data_source_ids": [source_id],
            },
        )
        assert team_entitlement.status_code == 200
        team_entitlement_id = team_entitlement.json()["entitlements"][0]["id"]

        duplicate_entitlement_with_invalid_status = client.post(
            "/api/admin/data-sources/entitlements",
            headers=headers,
            json={
                "tenant_id": "T1",
                "scope_type": "organization_unit",
                "organization_unit_id": "team-1",
                "data_source_ids": [source_id],
                "status": "unsupported",
            },
        )
        assert duplicate_entitlement_with_invalid_status.status_code == 422
        assert (
            duplicate_entitlement_with_invalid_status.json()["detail"]
            == "状态必须是 active 或 inactive。"
        )

        entitlements = client.get(
            "/api/admin/data-sources/entitlements",
            headers=headers,
            params={"tenant_id": "T1", "search": "Main Data", "page_size": 10},
        )
        assert entitlements.status_code == 200
        assert entitlements.json()["pagination"] == {"page": 1, "page_size": 10, "total": 3}
        assert {row["scope_type"] for row in entitlements.json()["entitlements"]} == {
            "tenant",
            "organization_unit",
        }

        binding = client.post(
            "/api/admin/data-sources/bindings",
            headers=headers,
            json={
                "tenant_id": "T1",
                "scope_type": "organization_unit",
                "organization_unit_id": "team-1",
                "data_source_id": source_id,
            },
        )
        assert binding.status_code == 200
        assert binding.json()["data_source_id"] == source_id

        duplicate_binding_with_invalid_status = client.post(
            "/api/admin/data-sources/bindings",
            headers=headers,
            json={
                "tenant_id": "T1",
                "scope_type": "organization_unit",
                "organization_unit_id": "team-1",
                "data_source_id": source_id,
                "status": "unsupported",
            },
        )
        assert duplicate_binding_with_invalid_status.status_code == 409
        assert duplicate_binding_with_invalid_status.json()["detail"] == "该范围已绑定数据源。"

        listed = client.get(
            "/api/admin/data-sources/bindings",
            headers=headers,
            params={"search": "Main Data"},
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["bindings"]] == [binding.json()["id"]]

        blocked = client.patch(
            f"/api/admin/data-sources/entitlements/{tenant_entitlement_id}",
            headers=headers,
            json={"status": "inactive"},
        )
        assert blocked.status_code == 422
        assert "下级分配" in blocked.json()["detail"]

        inactive_source_blocked = client.patch(
            f"/api/admin/data-sources/sources/{source_id}",
            headers=headers,
            json={"status": "inactive"},
        )
        assert inactive_source_blocked.status_code == 422
        assert inactive_source_blocked.json()["detail"] == "数据源仍存在启用绑定，不能停用。"

        delete_blocked = client.delete(
            f"/api/admin/data-sources/sources/{source_id}",
            headers=headers,
        )
        assert delete_blocked.status_code == 422
        assert "绑定关系" in delete_blocked.json()["detail"]

        binding_id = binding.json()["id"]
        inactive_binding = client.patch(
            f"/api/admin/data-sources/bindings/{binding_id}",
            headers=headers,
            json={"status": "inactive"},
        )
        assert inactive_binding.status_code == 200
        assert inactive_binding.json()["status"] == "inactive"

        delete_with_inactive_binding = client.delete(
            f"/api/admin/data-sources/sources/{source_id}",
            headers=headers,
        )
        assert delete_with_inactive_binding.status_code == 422
        assert (
            delete_with_inactive_binding.json()["detail"]
            == "数据源仍存在绑定关系，不能删除，请先解除数据源绑定。"
        )

        deleted_binding = client.delete(
            f"/api/admin/data-sources/bindings/{binding_id}",
            headers=headers,
        )
        assert deleted_binding.status_code == 200
        assert deleted_binding.json() == {"deleted": True}

        deleted_entitlement = client.delete(
            f"/api/admin/data-sources/entitlements/{team_entitlement_id}",
            headers=headers,
        )
        assert deleted_entitlement.status_code == 200
        assert deleted_entitlement.json() == {"deleted": True}

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            source = session.get(DataSourceSourceModel, source_id)
            assert source is not None
            assert source.status == "active"
            assert JsonSecretCipher(CREDENTIAL_KEY).decrypt(source.credentials_ciphertext) == {
                "app_key": "new-key",
                "app_secret": "secret",
            }
            tenant_entitlement_row = session.get(
                DataSourceSourceEntitlementModel,
                tenant_entitlement_id,
            )
            assert tenant_entitlement_row is not None
            assert tenant_entitlement_row.status == "active"
            assert (
                session.scalar(select(func.count()).select_from(DataSourceSourceEntitlementModel))
                == 2
            )
            assert (
                session.scalar(select(func.count()).select_from(DataSourceSourceBindingModel)) == 0
            )
            assert (
                int(session.scalar(select(func.count()).select_from(AdminAuditLogModel)) or 0) == 9
            )
    finally:
        engine.dispose()


def test_data_source_source_create_list_and_binding(tmp_path: Path) -> None:
    _assert_data_source_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_data_source_source_delete_rejects_existing_binding(tmp_path: Path) -> None:
    _assert_data_source_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_data_source_admin_openapi_publishes_management_routes() -> None:
    spec = create_admin_app().openapi()
    paths = {path for path in spec["paths"] if path.startswith("/api/admin/data-sources")}

    assert paths == {
        "/api/admin/data-sources/sources",
        "/api/admin/data-sources/sources/{source_id}",
        "/api/admin/data-sources/entitlements",
        "/api/admin/data-sources/entitlements/{entitlement_id}",
        "/api/admin/data-sources/bindings",
        "/api/admin/data-sources/bindings/{binding_id}",
    }


def _seed_database(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        ZhizhiBase.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                [
                    AdminUserModel(
                        id="admin-super",
                        username="root",
                        normalized_username="ROOT",
                        password_hash="hash",
                        is_super=True,
                    ),
                    TenantModel(
                        id="T1",
                        tenant_code="T1",
                        normalized_tenant_code="T1",
                        tenant_name="Tenant One",
                        storage_key="TENANT_ONE",
                    ),
                    OrganizationUnitModel(
                        id="division-1",
                        tenant_id="T1",
                        external_key="DIVISION",
                        normalized_external_key="DIVISION",
                        storage_key="DIVISION",
                        name="Division One",
                        unit_type="division",
                    ),
                    OrganizationUnitModel(
                        id="team-1",
                        tenant_id="T1",
                        parent_id="division-1",
                        external_key="TEAM",
                        normalized_external_key="TEAM",
                        storage_key="TEAM",
                        name="Team One",
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
