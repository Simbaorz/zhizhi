"""Real authenticated Admin resource lifecycle without connecting to production DBs."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from gewu_core import JsonSecretCipher, StorageEncryptionSettings
from gewu_core.config import BootstrapSettings
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform.data_source.repository import DataSourceModel
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import JwtSettings
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminUserModel,
    OrganizationUnitModel,
    TenantModel,
)
from zhizhi_platform.iam.passwords import hash_password


def test_admin_configs_encrypted_connections_and_delegates_multi_source_bindings(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    ZhizhiBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            AdminUserModel(
                id="root",
                username="root",
                normalized_username="root",
                display_name="Root",
                password_hash=hash_password("test-password"),
                is_super=True,
                status="active",
            )
        )
        session.add(
            TenantModel(
                id="tenant",
                tenant_code="TENANT",
                normalized_tenant_code="tenant",
                storage_key="tenant",
                tenant_name="Tenant",
                status="active",
            )
        )
        session.add(
            OrganizationUnitModel(
                id="division",
                tenant_id="tenant",
                external_key="division",
                normalized_external_key="division",
                storage_key="division",
                name="Division",
                status="active",
            )
        )
        session.add(
            OrganizationUnitModel(
                id="leaf",
                tenant_id="tenant",
                parent_id="division",
                external_key="leaf",
                normalized_external_key="leaf",
                storage_key="leaf",
                name="Leaf",
                status="active",
            )
        )
        session.commit()
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk="j" * 32), storage_encryption=StorageEncryptionSettings(key="e" * 32)
        ),
    )
    with TestClient(create_admin_app(bootstrap=bootstrap, runtime=runtime)) as client:
        assert runtime._iam and runtime._iam.identity_security
        token = runtime._iam.identity_security.issue_admin_token(
            user_id="root", username="root", is_super=True
        )
        client.cookies.set("zhizhi_admin_session", token, path="/api/admin")
        client.cookies.set("zhizhi_admin_csrf", "test-csrf", path="/")
        headers = {"X-CSRF-Token": "test-csrf"}
        sources = []
        malformed = client.post(
            "/api/admin/data-sources",
            headers=headers,
            json={
                "source_key": "bad",
                "tag": "OB",
                "host": "db",
                "database": "db",
                "username": "reader",
                "password": {"secret": "never-echo-this"},
            },
        )
        assert malformed.status_code == 422 and "never-echo-this" not in malformed.text
        for key, tag in (("orders", "OB"), ("analytics", "ADB")):
            response = client.post(
                "/api/admin/data-sources",
                headers=headers,
                json={
                    "source_key": key,
                    "tag": tag,
                    "host": "db.example.test",
                    "database": key,
                    "username": "reader",
                    "password": "test-db-password",
                },
            )
            assert response.status_code == 200, response.text
            value = response.json()
            assert "password" not in value and "credentials_ciphertext" not in value
            sources.append(value)
        ids = [source["id"] for source in sources]
        for source_id in ids:
            denied = client.post(
                "/api/admin/data-sources/entitlements",
                headers=headers,
                json={
                    "tenant_id": "tenant",
                    "organization_unit_id": "leaf",
                    "source_id": source_id,
                },
            )
            assert denied.status_code == 403
            for unit_id in ("", "division", "leaf"):
                response = client.post(
                    "/api/admin/data-sources/entitlements",
                    headers=headers,
                    json={
                        "tenant_id": "tenant",
                        "organization_unit_id": unit_id,
                        "source_id": source_id,
                    },
                )
                assert response.status_code == 200, response.text
        response = client.put(
            "/api/admin/data-sources/bindings",
            headers=headers,
            json={
                "tenant_id": "tenant",
                "organization_unit_id": "leaf",
                "source_ids": ids,
                "default_source_id": ids[1],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["source_ids"] == ids
        assert response.json()["default_source_id"] == ids[1]
        response = client.delete(
            "/api/admin/data-sources/entitlements",
            headers=headers,
            params={"tenant_id": "tenant", "organization_unit_id": "leaf", "source_id": ids[0]},
        )
        assert response.status_code == 409
        assert (
            client.delete(f"/api/admin/data-sources/{ids[0]}", headers=headers).status_code == 409
        )
        duplicate = client.post(
            "/api/admin/data-sources",
            headers=headers,
            json={
                "source_key": "orders",
                "tag": "OB",
                "host": "db",
                "database": "orders",
                "username": "reader",
                "password": "another-password",
            },
        )
        assert duplicate.status_code == 409
        with Session(engine) as session:
            stored = session.get(DataSourceModel, ids[0])
            assert stored is not None
            ciphertext = stored.configuration["credentials_ciphertext"]
            assert "test-db-password" not in ciphertext
            assert JsonSecretCipher("e" * 32).decrypt(ciphertext)["password"] == "test-db-password"
        assert (
            client.post(f"/api/admin/data-sources/{ids[0]}/test", headers=headers).json()["success"]
            is False
        )
        assert (
            client.put(
                "/api/admin/data-sources/bindings",
                headers=headers,
                json={"tenant_id": "tenant", "source_ids": ids, "default_source_id": "not-bound"},
            ).status_code
            == 422
        )
    engine.dispose()
