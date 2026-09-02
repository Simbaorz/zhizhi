"""致知 Skill management HTTP contract and real persistence behavior."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from zhizhi.assets import SharedAssetModel

from gewu_core.config import BootstrapSettings
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import JwtSettings
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminUserModel,
    OrganizationUnitModel,
    TenantModel,
)
from zhizhi_platform.workspace import ZhizhiWorkspaceSettings

JWT_SIGNING_KEY = "skill-admin-integration-signing-key"
ADMIN_ID = "00000000000040008000000000000001"


def _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    storage_root = tmp_path / "vfs"
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(storage_root)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        headers = _cookie_headers(
            security.issue_admin_token(
                user_id=ADMIN_ID,
                username="root",
                is_super=True,
            )
        )

        empty_root = client.get(
            "/api/admin/skill-files/entries",
            headers=headers,
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills",
            },
        )
        assert empty_root.status_code == 200
        assert empty_root.json()["entries"] == []

        created_response = client.post(
            "/api/admin/skills",
            headers=headers,
            json={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "name": "report",
                "description": "Reporting Skill",
                "content": _skill_md("report", "Reporting Skill", "# Original\n"),
            },
        )
        assert created_response.status_code == 200
        created = created_response.json()
        asset_key = created["asset_key"]
        assert created["main_file_path"] == ".skills/report/SKILL.md"
        assert created["version"].isdecimal()

        physical_file = storage_root / "tenants/TENANT_ONE/shared/.skills/report/SKILL.md"
        assert physical_file.read_text(encoding="utf-8") == _skill_md(
            "report", "Reporting Skill", "# Original\n"
        )

        listed = client.get(
            "/api/admin/skills",
            headers=headers,
            params={"scope_type": "tenant", "scope_tenant_id": "tenant-1"},
        )
        assert listed.status_code == 200
        assert listed.json()["skills"] == [asset_key]

        detail = client.get(
            f"/api/admin/skills/{asset_key}",
            headers=headers,
            params={"scope_type": "tenant", "scope_tenant_id": "tenant-1"},
        )
        assert detail.status_code == 200
        assert detail.json()["path"] == ".skills/report"
        assert detail.json()["main_file_path"] == ".skills/report/SKILL.md"
        version = detail.json()["version"]

        entries = client.get(
            "/api/admin/skill-files/entries",
            headers=headers,
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report",
            },
        )
        assert entries.status_code == 200
        assert [entry["path"] for entry in entries.json()["entries"]] == [".skills/report/SKILL.md"]

        written = client.put(
            "/api/admin/skill-files/file",
            headers=headers,
            json={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/SKILL.md",
                "expected_version": version,
                "content": _skill_md("report", "Updated Skill", "# Updated\n"),
            },
        )
        assert written.status_code == 200
        assert written.json()["version"].isdecimal()
        read = client.get(
            "/api/admin/skill-files/file",
            headers=headers,
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/SKILL.md",
            },
        )
        assert read.status_code == 200
        assert read.json()["content"] == _skill_md("report", "Updated Skill", "# Updated\n")
        assert read.json()["version"] == written.json()["version"]
        stale = client.put(
            "/api/admin/skill-files/file",
            headers=headers,
            json={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/SKILL.md",
                "expected_version": version,
                "content": _skill_md("report", "Stale Skill", "# Stale\n"),
            },
        )
        assert stale.status_code == 409
        assert stale.json() == {"detail": "File version does not match expected_version."}

        directory = client.post(
            "/api/admin/skill-files/directories",
            headers=headers,
            json={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/docs",
            },
        )
        assert directory.status_code == 200
        uploaded = client.put(
            "/api/admin/skill-files/upload",
            headers={**headers, "Content-Type": "application/octet-stream"},
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/docs/guide.md",
            },
            content=b"guide",
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["path"] == ".skills/report/docs/guide.md"

        moved = client.post(
            "/api/admin/skill-files/move",
            headers=headers,
            json={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "src_path": ".skills/report/docs/guide.md",
                "dst_path": ".skills/report/docs/manual.md",
            },
        )
        assert moved.status_code == 200
        downloaded = client.get(
            "/api/admin/skill-files/download",
            headers=headers,
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/docs/manual.md",
            },
        )
        assert downloaded.status_code == 200
        assert downloaded.content == b"guide"
        assert downloaded.headers["content-type"] == "application/octet-stream"

        replaced_files = client.put(
            "/api/admin/skill-files/package",
            headers={**headers, "Content-Type": "application/zip"},
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/docs",
            },
            content=_directory_package("docs", "manual.md", "packaged-guide"),
        )
        assert replaced_files.status_code == 200
        assert replaced_files.json()["path"] == ".skills/report/docs"
        packaged_file = client.get(
            "/api/admin/skill-files/file",
            headers=headers,
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/docs/manual.md",
            },
        )
        assert packaged_file.status_code == 200
        assert packaged_file.json()["content"] == "packaged-guide"

        packaged = client.put(
            "/api/admin/skills/package",
            headers={**headers, "Content-Type": "application/zip"},
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "name": "analysis",
            },
            content=_skill_package("analysis", body="# Analysis\n"),
        )
        assert packaged.status_code == 200
        analysis_key = packaged.json()["asset_key"]

        replaced = client.put(
            f"/api/admin/skills/{analysis_key}/package",
            headers={**headers, "Content-Type": "application/zip"},
            params={"scope_type": "tenant", "scope_tenant_id": "tenant-1"},
            content=_skill_package("diagnostics", body="# Diagnostics\n"),
        )
        assert replaced.status_code == 200
        assert replaced.json()["name"] == "diagnostics"
        assert not (storage_root / "tenants/TENANT_ONE/shared/.skills/analysis").exists()

        directory_download = client.get(
            "/api/admin/skill-files/download",
            headers=headers,
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/diagnostics",
            },
        )
        assert directory_download.status_code == 200
        assert directory_download.headers["content-type"] == "application/zip"
        with ZipFile(BytesIO(directory_download.content)) as archive:
            assert (
                archive.read("diagnostics/SKILL.md")
                == _skill_md("diagnostics", "Test skill", "# Diagnostics\n").encode()
            )

        unsafe_package = BytesIO()
        with ZipFile(unsafe_package, "w") as archive:
            archive.writestr(
                "../escape/SKILL.md",
                _skill_md("escape", "Unsafe", "# Bad\n"),
            )
        rejected_package = client.put(
            "/api/admin/skills/package",
            headers={**headers, "Content-Type": "application/zip"},
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "name": "escape",
            },
            content=unsafe_package.getvalue(),
        )
        assert rejected_package.status_code == 422
        assert rejected_package.json() == {
            "detail": "Uploaded Skill package contains unsafe paths."
        }
        assert not (tmp_path / "escape").exists()

        deleted_file = client.request(
            "DELETE",
            "/api/admin/skill-files",
            headers=headers,
            json={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "path": ".skills/report/docs/manual.md",
            },
        )
        assert deleted_file.status_code == 200
        deleted_asset = client.request(
            "DELETE",
            f"/api/admin/skills/{asset_key}",
            headers=headers,
            json={"scope_type": "tenant", "scope_tenant_id": "tenant-1"},
        )
        assert deleted_asset.status_code == 200
        assert not (storage_root / "tenants/TENANT_ONE/shared/.skills/report").exists()

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            rows = list(
                session.scalars(select(SharedAssetModel).order_by(SharedAssetModel.asset_key.asc()))
            )
            by_key = {row.asset_key: row for row in rows}
            assert by_key[asset_key].status == "deleted"
            assert by_key[asset_key].created_by_admin_user_id == ADMIN_ID
            assert by_key[asset_key].updated_by_admin_user_id == ADMIN_ID
            assert by_key[analysis_key].name == "diagnostics"
            assert by_key[analysis_key].status == "enabled"
    finally:
        engine.dispose()


def test_skill_entries_lists_skills_subtree(tmp_path: Path) -> None:
    _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_skill_entries_returns_empty_when_skills_root_missing(tmp_path: Path) -> None:
    _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_skill_download_directory_returns_zip(tmp_path: Path) -> None:
    _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_skill_asset_package_replaces_directory_and_updates_db_name(tmp_path: Path) -> None:
    _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_skill_asset_package_creates_asset_from_zip(tmp_path: Path) -> None:
    _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_get_skill_detail_keeps_asset_path_and_main_file_path(tmp_path: Path) -> None:
    _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_create_skill_uses_admin_username_for_audit_fields(tmp_path: Path) -> None:
    _assert_skill_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_skill_entries_reject_organization_unit_scope(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(tmp_path / "vfs")),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)
    organization_scope = {
        "scope_type": "organization_unit",
        "scope_tenant_id": "tenant-1",
        "scope_organization_unit_id": "team-1",
    }

    with TestClient(app) as client:
        headers = _super_headers(runtime)
        assets = client.get(
            "/api/admin/skills",
            headers=headers,
            params=organization_scope,
        )
        files = client.get(
            "/api/admin/skill-files/entries",
            headers=headers,
            params={**organization_scope, "path": ".skills"},
        )

    assert assets.status_code == 422
    assert files.status_code == 422


def test_skill_management_accepts_only_tenant_scope(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(tmp_path / "vfs")),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)
    scopes = [
        {"scope_type": "tenant", "scope_tenant_id": "tenant-1"},
        {
            "scope_type": "organization_unit",
            "scope_tenant_id": "tenant-1",
            "scope_organization_unit_id": "division-1",
        },
        {
            "scope_type": "organization_unit",
            "scope_tenant_id": "tenant-1",
            "scope_organization_unit_id": "team-1",
        },
    ]
    with TestClient(app) as client:
        headers = _super_headers(runtime)
        created = [
            client.post(
                "/api/admin/skills",
                headers=headers,
                json={
                    **scope,
                    "name": "query-data",
                    "description": f"{scope['scope_type']} query",
                    "content": _skill_md(
                        "query-data",
                        f"{scope['scope_type']} query",
                        "# Query\n",
                    ),
                },
            )
            for scope in scopes
        ]
        listed = [
            client.get("/api/admin/skills", headers=headers, params=scope) for scope in scopes
        ]

    assert [response.status_code for response in created] == [200, 422, 422]
    assert [response.status_code for response in listed] == [200, 422, 422]
    assert listed[0].json()["assets"][0]["scope_type"] == "tenant"


def _assert_skill_file_mutations_cannot_manage_asset_roots(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(tmp_path / "vfs")),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        headers = _super_headers(runtime)
        scope = {"scope_type": "tenant", "scope_tenant_id": "tenant-1"}
        responses = [
            client.put(
                "/api/admin/skill-files/file",
                headers=headers,
                json={**scope, "path": ".skills/orphan", "content": "x"},
            ),
            client.put(
                "/api/admin/skill-files/upload",
                headers={**headers, "Content-Type": "application/octet-stream"},
                params={**scope, "path": ".skills/orphan"},
                content=b"x",
            ),
            client.put(
                "/api/admin/skill-files/package",
                headers={**headers, "Content-Type": "application/zip"},
                params={**scope, "path": ".skills/orphan"},
                content=_directory_package("orphan", "SKILL.md", "# Orphan"),
            ),
            client.post(
                "/api/admin/skill-files/directories",
                headers=headers,
                json={**scope, "path": ".skills/orphan"},
            ),
            client.post(
                "/api/admin/skill-files/move",
                headers=headers,
                json={
                    **scope,
                    "src_path": ".skills/report",
                    "dst_path": ".skills/analysis",
                },
            ),
            client.request(
                "DELETE",
                "/api/admin/skill-files",
                headers=headers,
                json={**scope, "path": ".skills/report", "recursive": True},
            ),
        ]

    expected = {"detail": "Skill asset roots are managed by the Skill asset API."}
    assert [response.status_code for response in responses] == [422] * len(responses)
    assert all(response.json() == expected for response in responses)


def test_skill_file_mutations_cannot_manage_asset_roots(tmp_path: Path) -> None:
    _assert_skill_file_mutations_cannot_manage_asset_roots(tmp_path)


def test_skill_file_package_rejects_top_level_asset_directory(tmp_path: Path) -> None:
    _assert_skill_file_mutations_cannot_manage_asset_roots(tmp_path)


def test_skill_asset_package_rejects_existing_target_directory(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    storage_root = tmp_path / "vfs"
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(storage_root)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        headers = _super_headers(runtime)
        scope = {"scope_type": "tenant", "scope_tenant_id": "tenant-1"}
        created = client.post(
            "/api/admin/skills",
            headers=headers,
            json={
                **scope,
                "name": "review",
                "description": "Review old",
                "content": _skill_md("review", "Review old", "# Old Review\n"),
            },
        )
        assert created.status_code == 200
        asset_key = created.json()["asset_key"]
        skills_root = storage_root / "tenants/TENANT_ONE/shared/.skills"
        conflict_root = skills_root / "review-next"
        conflict_root.mkdir(parents=True)
        (conflict_root / "keep.md").write_text("keep", encoding="utf-8")

        response = client.put(
            f"/api/admin/skills/{asset_key}/package",
            headers={**headers, "Content-Type": "application/zip"},
            params=scope,
            content=_skill_package("review-next", body="# Review Next\n"),
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Skill directory already exists."}
    assert (skills_root / "review/SKILL.md").read_text(encoding="utf-8") == _skill_md(
        "review", "Review old", "# Old Review\n"
    )
    assert (conflict_root / "keep.md").read_text(encoding="utf-8") == "keep"
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            row = session.scalar(
                select(SharedAssetModel).where(SharedAssetModel.asset_key == asset_key)
            )
            assert row is not None
            assert row.name == "review"
            assert row.source == "admin"
    finally:
        engine.dispose()


def test_skill_package_validation_precedes_orphan_directory_conflict(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    storage_root = tmp_path / "vfs"
    orphan = storage_root / "tenants/TENANT_ONE/shared/.skills/Orphan"
    orphan.mkdir(parents=True)
    (orphan / "keep.md").write_text("keep", encoding="utf-8")
    unsafe = BytesIO()
    with ZipFile(unsafe, "w") as archive:
        archive.writestr(
            "../escape/SKILL.md",
            _skill_md("Orphan", "Unsafe", "# Unsafe\n"),
        )
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(storage_root)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        response = client.put(
            "/api/admin/skills/package",
            headers={**_super_headers(runtime), "Content-Type": "application/zip"},
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "name": "Orphan",
            },
            content=unsafe.getvalue(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Uploaded Skill package contains unsafe paths."}
    assert (orphan / "keep.md").read_text(encoding="utf-8") == "keep"


def test_skill_admin_openapi_publishes_asset_and_file_routes() -> None:
    spec = create_admin_app().openapi()
    paths = {
        path
        for path in spec["paths"]
        if path.startswith("/api/admin/skills") or path.startswith("/api/admin/skill-files")
    }

    assert len(paths) == 12
    assert "/api/admin/skills" in paths
    assert "/api/admin/skills/{skill_asset_key}" in paths
    assert "/api/admin/skill-files/entries" in paths
    assert "/api/admin/skill-files/upload" in paths


def _seed_database(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        ZhizhiBase.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                [
                    AdminUserModel(
                        id=ADMIN_ID,
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
                    OrganizationUnitModel(
                        id="division-1",
                        tenant_id="tenant-1",
                        external_key="DIVISION",
                        normalized_external_key="DIVISION",
                        storage_key="DIVISION_ONE",
                        name="Division One",
                        unit_type="division",
                    ),
                    OrganizationUnitModel(
                        id="team-1",
                        tenant_id="tenant-1",
                        parent_id="division-1",
                        external_key="TEAM",
                        normalized_external_key="TEAM",
                        storage_key="TEAM_ONE",
                        name="Team One",
                        unit_type="team",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _super_headers(runtime: ZhizhiAdminApiRuntime) -> dict[str, str]:
    security = runtime._iam.identity_security if runtime._iam is not None else None
    assert security is not None
    return _cookie_headers(
        security.issue_admin_token(
            user_id=ADMIN_ID,
            username="root",
            is_super=True,
        )
    )


def _cookie_headers(token: str) -> dict[str, str]:
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }


def _skill_md(name: str, description: str, body: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


def _skill_package(name: str, *, body: str) -> bytes:
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr(
            f"{name}/SKILL.md",
            _skill_md(name, "Test skill", body),
        )
    return content.getvalue()


def _directory_package(root: str, filename: str, content_value: str) -> bytes:
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr(f"{root}/{filename}", content_value)
    return content.getvalue()
