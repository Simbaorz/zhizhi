"""Real Admin managed-Git flow through SQLite, JWT, encryption, RBAC, and audit."""

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
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.git import RestrictedGitRepositoryClient
from zhizhi_platform.git.adapters.mysql.models import (
    GitRepositoryModel,
    WorkspaceSceneGitConfigModel,
)
from zhizhi_platform.iam import JwtSettings
from zhizhi_platform.iam.adapters.mysql.models import AdminUserModel, TenantModel

JWT_SIGNING_KEY = "g" * 32
CREDENTIAL_KEY = "c" * 32


def _assert_managed_git_round_trip_matches_zhizhi_behavior(
    tmp_path: Path,
    monkeypatch,
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
    monkeypatch.setattr(
        RestrictedGitRepositoryClient,
        "probe",
        lambda self, repo_url, username="", password="": 3,
    )

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
            "/api/admin/git-repositories",
            headers=headers,
            json={
                "alias": "internal",
                "display_name": "Internal Git",
                "repo_url": "http://10.0.0.8:8080/group/repo.git",
                "default_branch": "main",
                "username": "git-user",
                "password": "secret-token",
                "status": "active",
            },
        )
        assert created_response.status_code == 200
        created = created_response.json()
        repository_id = created["id"]
        assert created["has_credential"] is True
        assert "credential_ciphertext" not in created
        assert "password" not in created

        repositories = client.get(
            "/api/admin/git-repositories",
            headers=headers,
            params={"search": "Internal", "page_size": 1},
        )
        assert repositories.status_code == 200
        assert repositories.json()["pagination"] == {"page": 1, "page_size": 1, "total": 1}
        assert [row["id"] for row in repositories.json()["repositories"]] == [repository_id]
        assert "secret-token" not in str(repositories.json())

        patched = client.patch(
            f"/api/admin/git-repositories/{repository_id}",
            headers=headers,
            json={"display_name": "Renamed Git", "default_branch": "release"},
        )
        assert patched.status_code == 200
        assert patched.json()["display_name"] == "Renamed Git"
        assert patched.json()["default_branch"] == "release"

        credentials = client.patch(
            f"/api/admin/git-repositories/{repository_id}/credentials",
            headers=headers,
            json={"username": "renamed-user", "password": ""},
        )
        assert credentials.status_code == 200
        assert credentials.json()["username"] == "renamed-user"

        probe = client.post(
            f"/api/admin/git-repositories/{repository_id}/test",
            headers=headers,
        )
        assert probe.status_code == 200
        assert probe.json()["ok"] is True
        assert "3" in probe.json()["message"]

        assigned = client.post(
            "/api/admin/git-repositories/entitlements/batch",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "git_repository_ids": [repository_id],
                "status": "active",
            },
        )
        assert assigned.status_code == 200
        entitlement_id = assigned.json()["entitlements"][0]["id"]

        listed = client.get(
            "/api/admin/git-repositories/entitlements/list",
            headers=headers,
            params={"tenant_id": "tenant-1", "search": "Internal", "page_size": 1},
        )
        assert listed.status_code == 200
        assert listed.json()["pagination"] == {"page": 1, "page_size": 1, "total": 1}
        assert listed.json()["repositories"][0]["username"] == ""
        assert listed.json()["assignable_repositories"] == []

        available = client.get(
            "/api/admin/git-repositories/available/list",
            headers=headers,
            params={"tenant_id": "tenant-1"},
        )
        assert available.status_code == 200
        assert [row["id"] for row in available.json()["repositories"]] == [repository_id]

        _insert_scene_usage(tmp_path, repository_id)
        inactive = client.patch(
            f"/api/admin/git-repositories/entitlements/{entitlement_id}",
            headers=headers,
            json={"status": "inactive"},
        )
        assert inactive.status_code == 409
        assert "Scene" in inactive.json()["detail"]
        blocked_entitlement_delete = client.delete(
            f"/api/admin/git-repositories/entitlements/{entitlement_id}",
            headers=headers,
        )
        assert blocked_entitlement_delete.status_code == 409
        blocked_repository_delete = client.delete(
            f"/api/admin/git-repositories/{repository_id}",
            headers=headers,
        )
        assert blocked_repository_delete.status_code == 409

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            row = session.get(GitRepositoryModel, repository_id)
            assert row is not None
            assert JsonSecretCipher(CREDENTIAL_KEY).decrypt(row.credential_ciphertext) == {
                "password": "secret-token",
                "username": "renamed-user",
            }
            audit_count = int(
                session.scalar(select(func.count()).select_from(AdminAuditLogModel)) or 0
            )
            assert audit_count == 5
    finally:
        engine.dispose()


def test_scene_git_catalog_lists_are_server_paginated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _assert_managed_git_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_managed_git_openapi_publishes_the_repository_management_surface() -> None:
    spec = create_admin_app().openapi()
    paths = {path for path in spec["paths"] if path.startswith("/api/admin/git-repositories")}

    assert paths == {
        "/api/admin/git-repositories",
        "/api/admin/git-repositories/{repository_id}",
        "/api/admin/git-repositories/{repository_id}/credentials",
        "/api/admin/git-repositories/{repository_id}/test",
        "/api/admin/git-repositories/entitlements/list",
        "/api/admin/git-repositories/entitlements/batch",
        "/api/admin/git-repositories/entitlements/{entitlement_id}",
        "/api/admin/git-repositories/available/list",
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
                        id="tenant-1",
                        tenant_code="T1",
                        normalized_tenant_code="T1",
                        tenant_name="Tenant One",
                        storage_key="TENANT_ONE",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _insert_scene_usage(tmp_path: Path, repository_id: str) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add(
                WorkspaceSceneGitConfigModel(
                    tenant_id="tenant-1",
                    scope_type="tenant",
                    scene_asset_key="scene-1",
                    git_repository_id=repository_id,
                )
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
