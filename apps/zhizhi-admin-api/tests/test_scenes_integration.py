"""Zhizhi Scene management HTTP contract and real persistence behavior."""

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
from zhizhi_platform.git.adapters.mysql.models import (
    GitEntitlementModel,
    GitRepositoryModel,
    WorkspaceSceneGitConfigModel,
)
from zhizhi_platform.iam import JwtSettings
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminRoleModel,
    AdminRolePermissionModel,
    AdminTenantMemberModel,
    AdminTenantRoleModel,
    AdminUserModel,
    OrganizationUnitModel,
    TenantModel,
)
from zhizhi_platform.workspace import (
    BackgroundJobModel,
    ZhizhiWorkspaceSettings,
)

JWT_SIGNING_KEY = "scene-admin-integration-signing-key"
ADMIN_ID = "00000000000040008000000000000003"
GIT_SCENE_KEY = "scene_00000000000040008000000000000004"
GIT_REPOSITORY_ID = "00000000000040008000000000000007"


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    async def enqueue(self, job_id: str) -> str:
        self.job_ids.append(job_id)
        return f"task-{len(self.job_ids)}"


class _FailingDispatcher:
    async def enqueue(self, job_id: str) -> str:
        raise RuntimeError(f"broker unavailable for {job_id}")


def _assert_scene_admin_round_trip_matches_zhizhi_behavior(tmp_path: Path) -> None:
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
        created_response = client.post(
            "/api/admin/scenes",
            headers=headers,
            json={
                **scope,
                "name": "Fault Scene",
                "description": "Operational troubleshooting",
                "required_skill_asset_key": "skill_00000000000040008000000000000005",
                "recommended_skill_asset_keys": ["skill_00000000000040008000000000000006"],
            },
        )
        assert created_response.status_code == 200, created_response.text
        created = created_response.json()
        asset_key = created["asset_key"]
        assert asset_key.startswith("scene_")
        assert created["id"] == asset_key
        assert created["path"] == ".scenes/Fault Scene"
        assert created["mode"] == "auto"
        assert created["source"] == "admin"
        assert created["readonly"] is False
        assert created["git"] is None
        scene_root = storage_root / "tenants/TENANT_ONE/shared/.scenes/Fault Scene"
        assert scene_root.is_dir()

        duplicate = client.post(
            "/api/admin/scenes",
            headers=headers,
            json={**scope, "name": "Fault Scene"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": "Scene name already exists."}

        created_directory = client.post(
            "/api/admin/scenes/directories",
            headers=headers,
            json={**scope, "scene_id": asset_key, "path": "wiki"},
        )
        assert created_directory.status_code == 200

        written = client.put(
            "/api/admin/scenes/file",
            headers=headers,
            json={
                **scope,
                "scene_id": asset_key,
                "path": "wiki/index.md",
                "content": "first",
            },
        )
        assert written.status_code == 200
        version = written.json()["version"]
        assert isinstance(version, str) and version.isdecimal()
        read = client.get(
            "/api/admin/scenes/file",
            headers=headers,
            params={**scope, "scene_id": asset_key, "path": "wiki/index.md"},
        )
        assert read.status_code == 200
        assert read.json()["content"] == "first"
        assert read.json()["path"] == "wiki/index.md"

        stale = client.put(
            "/api/admin/scenes/file",
            headers=headers,
            json={
                **scope,
                "scene_id": asset_key,
                "path": "wiki/index.md",
                "content": "stale",
                "expected_version": str(int(version) + 1),
            },
        )
        assert stale.status_code == 409
        assert stale.json() == {"detail": "File version does not match expected_version."}

        uploaded = client.put(
            "/api/admin/scenes/upload",
            headers={**headers, "Content-Type": "application/octet-stream"},
            params={**scope, "scene_id": asset_key, "path": "wiki/raw.bin"},
            content=b"raw-content",
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["path"] == "wiki/raw.bin"
        moved = client.post(
            "/api/admin/scenes/move",
            headers=headers,
            json={
                **scope,
                "scene_id": asset_key,
                "src_path": "wiki/raw.bin",
                "dst_path": "wiki/data.bin",
            },
        )
        assert moved.status_code == 200
        downloaded = client.get(
            "/api/admin/scenes/download",
            headers=headers,
            params={**scope, "scene_id": asset_key, "path": "wiki/data.bin"},
        )
        assert downloaded.status_code == 200
        assert downloaded.content == b"raw-content"

        binary_uploaded = client.put(
            "/api/admin/scenes/upload",
            headers={**headers, "Content-Type": "application/octet-stream"},
            params={**scope, "scene_id": asset_key, "path": "wiki/document.docx"},
            content=b"\xff\xfebinary-document",
        )
        assert binary_uploaded.status_code == 200
        unsupported_preview = client.get(
            "/api/admin/scenes/file",
            headers=headers,
            params={**scope, "scene_id": asset_key, "path": "wiki/document.docx"},
        )
        assert unsupported_preview.status_code == 422
        assert unsupported_preview.json() == {"detail": "该文件不支持查看，请下载后打开。"}

        listed_entries = client.get(
            "/api/admin/scenes/entries",
            headers=headers,
            params={**scope, "scene_id": asset_key},
        )
        assert listed_entries.status_code == 200
        assert [entry["path"] for entry in listed_entries.json()["entries"]] == ["wiki"]

        replaced_directory = client.put(
            "/api/admin/scenes/directory-package",
            headers={**headers, "Content-Type": "application/zip"},
            params={**scope, "scene_id": asset_key, "path": "wiki"},
            content=_scene_package("replacement", {"index.md": "replacement"}),
        )
        assert replaced_directory.status_code == 200
        assert replaced_directory.json()["path"] == "wiki"
        assert (scene_root / "wiki/index.md").read_text(encoding="utf-8") == "replacement"
        assert not (scene_root / "wiki/data.bin").exists()

        root_mutation = client.post(
            "/api/admin/scenes/directories",
            headers=headers,
            json={**scope, "scene_id": asset_key, "path": "."},
        )
        assert root_mutation.status_code == 422
        assert root_mutation.json() == {
            "detail": "Scene asset roots are managed by the Scene asset API."
        }

        patched = client.patch(
            f"/api/admin/scenes/{asset_key}",
            headers=headers,
            json={**scope, "name": "Fault Scene V2", "description": "Updated"},
        )
        assert patched.status_code == 200
        assert patched.json()["path"] == ".scenes/Fault Scene V2"
        renamed_root = storage_root / "tenants/TENANT_ONE/shared/.scenes/Fault Scene V2"
        assert not scene_root.exists()
        assert (renamed_root / "wiki/index.md").read_text(encoding="utf-8") == "replacement"

        replaced_asset = client.put(
            f"/api/admin/scenes/{asset_key}/package",
            headers={**headers, "Content-Type": "application/zip"},
            params=scope,
            content=_scene_package("package", {"guide.md": "whole replacement"}),
        )
        assert replaced_asset.status_code == 200
        assert replaced_asset.json()["source"] == "upload"
        assert (renamed_root / "guide.md").read_text(encoding="utf-8") == "whole replacement"
        assert not (renamed_root / "wiki").exists()

        packaged_response = client.put(
            "/api/admin/scenes/package",
            headers={**headers, "Content-Type": "application/zip"},
            params={**scope, "name": "Packaged Scene"},
            content=_scene_package("bundle", {"docs/index.md": "packaged"}),
        )
        assert packaged_response.status_code == 200
        packaged = packaged_response.json()
        packaged_key = packaged["asset_key"]
        assert packaged["source"] == "upload"
        assert packaged["entry"]["path"] == ".scenes/Packaged Scene"
        packaged_root = storage_root / "tenants/TENANT_ONE/shared/.scenes/Packaged Scene"
        assert (packaged_root / "docs/index.md").read_text(encoding="utf-8") == "packaged"

        unsafe = BytesIO()
        with ZipFile(unsafe, "w") as archive:
            archive.writestr("../escape/index.md", "unsafe")
        rejected = client.put(
            "/api/admin/scenes/package",
            headers={**headers, "Content-Type": "application/zip"},
            params={**scope, "name": "Escape"},
            content=unsafe.getvalue(),
        )
        assert rejected.status_code == 422
        assert rejected.json() == {"detail": "Uploaded Scene package contains unsafe paths."}

        listed = client.get("/api/admin/scenes", headers=headers, params=scope)
        assert listed.status_code == 200
        assert {scene["asset_key"] for scene in listed.json()["scenes"]} == {
            asset_key,
            packaged_key,
        }

        deleted_path = client.request(
            "DELETE",
            "/api/admin/scenes/path",
            headers=headers,
            json={**scope, "scene_id": asset_key, "path": "guide.md"},
        )
        assert deleted_path.status_code == 200
        assert not (renamed_root / "guide.md").exists()

        for key in (asset_key, packaged_key):
            deleted = client.request(
                "DELETE",
                f"/api/admin/scenes/{key}",
                headers=headers,
                json=scope,
            )
            assert deleted.status_code == 200
        assert not renamed_root.exists()
        assert not packaged_root.exists()

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            rows = list(
                session.scalars(select(SharedAssetModel).where(SharedAssetModel.kind == "scene"))
            )
            by_key = {row.asset_key: row for row in rows}
            assert by_key[asset_key].status == "deleted"
            assert by_key[asset_key].name == "Fault Scene V2"
            assert by_key[packaged_key].status == "deleted"
    finally:
        engine.dispose()


def test_scene_asset_package_creates_asset_from_zip(tmp_path: Path) -> None:
    _assert_scene_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_scene_metadata_path_uses_name_and_rename_moves_directory(tmp_path: Path) -> None:
    _assert_scene_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_create_scene_uses_name_as_physical_directory(tmp_path: Path) -> None:
    _assert_scene_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_scene_asset_file_round_trip(tmp_path: Path) -> None:
    _assert_scene_admin_round_trip_matches_zhizhi_behavior(tmp_path)


def test_scene_admin_rejects_organization_unit_scope(tmp_path: Path) -> None:
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
        response = client.get(
            "/api/admin/scenes",
            headers=_super_headers(runtime),
            params={
                "scope_type": "organization_unit",
                "scope_tenant_id": "tenant-1",
                "scope_organization_unit_id": "team-1",
            },
        )

    assert response.status_code == 422


def test_scene_admin_base_openapi_publishes_file_management_routes() -> None:
    spec = create_admin_app().openapi()
    paths = {
        path
        for path in spec["paths"]
        if path.startswith("/api/admin/scenes")
        and all(segment not in path for segment in ("/git", "/sync-jobs", "/sync"))
    }
    assert len(paths) == 12
    assert "/api/admin/scenes" in paths
    assert "/api/admin/scenes/{scene_asset_key}" in paths
    assert "/api/admin/scenes/entries" in paths
    assert "/api/admin/scenes/upload" in paths


def _assert_scene_git_admin_round_trip_and_active_job_reuse(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    storage_root = tmp_path / "vfs"
    dispatcher = _RecordingDispatcher()
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(storage_root)),
        ),
        scene_git_dispatcher=dispatcher,
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        headers = _super_headers(runtime)
        scope = {"scope_type": "tenant", "scope_tenant_id": "tenant-1"}
        created_response = client.post(
            "/api/admin/scenes/git",
            headers=headers,
            json={
                **scope,
                "name": "Git Operations",
                "description": "Synchronized operating knowledge",
                "git_repository_id": GIT_REPOSITORY_ID,
                "branch": "main",
                "subdir": "knowledge/runbooks",
                "auto_sync_enabled": True,
                "daily_sync_time": "04:30",
                "timezone": "Asia/Shanghai",
            },
        )
        assert created_response.status_code == 200, created_response.text
        created = created_response.json()
        scene_asset_key = created["asset_key"]
        assert created["source"] == "git"
        assert created["readonly"] is True
        assert created["git"]["git_repository_id"] == GIT_REPOSITORY_ID
        assert created["git"]["daily_sync_time"] == "04:30"
        assert created["git"]["next_sync_at"] is not None
        scene_root = storage_root / "tenants/TENANT_ONE/shared/.scenes/Git Operations"
        assert scene_root.is_dir()

        listed = client.get("/api/admin/scenes", headers=headers, params=scope)
        assert listed.status_code == 200
        listed_scene = next(
            scene for scene in listed.json()["scenes"] if scene["asset_key"] == scene_asset_key
        )
        assert listed_scene["git"]["branch"] == "main"

        metadata = client.patch(
            f"/api/admin/scenes/{scene_asset_key}",
            headers=headers,
            json={
                **scope,
                "required_skill_asset_key": "skill_wiki",
                "source": "admin",
            },
        )
        assert metadata.status_code == 200, metadata.text
        assert metadata.json()["source"] == "git"
        assert metadata.json()["required_skill_asset_key"] == "skill_wiki"

        config = client.get(
            f"/api/admin/scenes/{scene_asset_key}/git",
            headers=headers,
            params=scope,
        )
        assert config.status_code == 200
        assert config.json()["subdir"] == "knowledge/runbooks"

        engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
        try:
            with Session(engine) as session:
                config_row = session.scalar(
                    select(WorkspaceSceneGitConfigModel).where(
                        WorkspaceSceneGitConfigModel.scene_asset_key == scene_asset_key
                    )
                )
                assert config_row is not None
                config_row.last_commit_sha = "a" * 40
                session.commit()
        finally:
            engine.dispose()

        patched = client.patch(
            f"/api/admin/scenes/{scene_asset_key}/git",
            headers=headers,
            json={
                **scope,
                "branch": "release",
                "ref": "v1.2.3",
                "subdir": "./",
                "auto_sync_enabled": False,
            },
        )
        assert patched.status_code == 200
        assert patched.json()["branch"] == "release"
        assert patched.json()["ref"] == "v1.2.3"
        assert patched.json()["subdir"] == ""
        assert patched.json()["last_commit_sha"] == ""
        assert patched.json()["auto_sync_enabled"] is False
        assert patched.json()["next_sync_at"] is None

        invalid_timezone = client.patch(
            f"/api/admin/scenes/{scene_asset_key}/git",
            headers=headers,
            json={**scope, "timezone": "Not/A-Timezone"},
        )
        assert invalid_timezone.status_code == 422
        assert invalid_timezone.json() == {"detail": "Timezone is invalid."}

        first_sync = client.post(
            f"/api/admin/scenes/{scene_asset_key}/sync",
            headers=headers,
            json=scope,
        )
        assert first_sync.status_code == 200
        first_job = first_sync.json()["job"]
        assert first_job["status"] == "queued"
        assert first_job["celery_task_id"] == "task-1"

        duplicate_sync = client.post(
            f"/api/admin/scenes/{scene_asset_key}/sync",
            headers=headers,
            json=scope,
        )
        assert duplicate_sync.status_code == 200
        assert duplicate_sync.json()["job"]["job_id"] == first_job["job_id"]
        assert dispatcher.job_ids == [first_job["job_id"]]

        fetched_job = client.get(
            f"/api/admin/scenes/sync-jobs/{first_job['job_id']}",
            headers=headers,
        )
        assert fetched_job.status_code == 200
        assert fetched_job.json()["job"] == first_job
        listed_jobs = client.get(
            f"/api/admin/scenes/{scene_asset_key}/sync-jobs",
            headers=headers,
            params=scope,
        )
        assert listed_jobs.status_code == 200
        assert [job["job_id"] for job in listed_jobs.json()["jobs"]] == [first_job["job_id"]]

        deleted = client.request(
            "DELETE",
            f"/api/admin/scenes/{scene_asset_key}",
            headers=headers,
            json=scope,
        )
        assert deleted.status_code == 200
        assert not scene_root.exists()

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            scene = session.scalar(
                select(SharedAssetModel).where(SharedAssetModel.asset_key == scene_asset_key)
            )
            config_row = session.scalar(
                select(WorkspaceSceneGitConfigModel).where(
                    WorkspaceSceneGitConfigModel.scene_asset_key == scene_asset_key
                )
            )
            assert scene is not None and scene.status == "deleted"
            assert config_row is None
    finally:
        engine.dispose()


def test_create_git_scene_persists_global_git_resource_reference(tmp_path: Path) -> None:
    _assert_scene_git_admin_round_trip_and_active_job_reuse(tmp_path)


def test_delete_git_scene_removes_git_config(tmp_path: Path) -> None:
    _assert_scene_git_admin_round_trip_and_active_job_reuse(tmp_path)


def test_scene_git_dispatch_failure_marks_job_failed(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    storage_root = tmp_path / "vfs"
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            workspace=ZhizhiWorkspaceSettings(storage_root=str(storage_root)),
        ),
        scene_git_dispatcher=_FailingDispatcher(),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        headers = _super_headers(runtime)
        scope = {"scope_type": "tenant", "scope_tenant_id": "tenant-1"}
        created = client.post(
            "/api/admin/scenes/git",
            headers=headers,
            json={
                **scope,
                "name": "Failing Git Scene",
                "git_repository_id": GIT_REPOSITORY_ID,
            },
        )
        assert created.status_code == 200
        response = client.post(
            f"/api/admin/scenes/{created.json()['asset_key']}/sync",
            headers=headers,
            json=scope,
        )
        assert response.status_code == 503
        expected_error = str(response.json()["detail"])
        assert expected_error.startswith("broker unavailable for job_")

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            jobs = list(session.scalars(select(BackgroundJobModel)))
            assert len(jobs) == 1
            assert jobs[0].status == "failed"
            assert jobs[0].active_key is None
            assert jobs[0].error == expected_error
    finally:
        engine.dispose()


def test_scene_git_job_query_rejects_cross_tenant_payload(tmp_path: Path) -> None:
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
        _seed_scoped_scene_admin(tmp_path)
        _seed_cross_tenant_scene_job(tmp_path)
        response = client.get(
            "/api/admin/scenes/sync-jobs/job-cross-tenant",
            headers=_admin_headers(runtime),
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing scoped permission: scenes.view"}


def test_scene_git_job_query_hides_other_job_types(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    _seed_background_job(
        tmp_path,
        job_id="job-other-type",
        job_type="unrelated_job",
        target_id=GIT_SCENE_KEY,
        payload={"tenant_id": "tenant-1", "scope_type": "tenant", "owner_user_id": None},
    )
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
        response = client.get(
            "/api/admin/scenes/sync-jobs/job-other-type",
            headers=_super_headers(runtime),
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Scene Git sync job does not exist."}


def test_scene_git_job_list_filters_inconsistent_scope_payload(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    _seed_shared_git_scene(tmp_path)
    _seed_background_job(
        tmp_path,
        job_id="job-inconsistent",
        job_type="scene_git_sync",
        target_id=GIT_SCENE_KEY,
        payload={"tenant_id": "tenant-2", "scope_type": "tenant", "owner_user_id": None},
    )
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
        response = client.get(
            f"/api/admin/scenes/{GIT_SCENE_KEY}/sync-jobs",
            params={"scope_type": "tenant", "scope_tenant_id": "tenant-1"},
            headers=_super_headers(runtime),
        )

    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_scene_git_validation_precedes_asset_lookup_and_mutation(tmp_path: Path) -> None:
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
        invalid_create_time = client.post(
            "/api/admin/scenes/git",
            headers=headers,
            json={
                **scope,
                "name": "/",
                "git_repository_id": "missing",
                "daily_sync_time": "bad",
            },
        )
        assert invalid_create_time.status_code == 422
        assert invalid_create_time.json() == {"detail": "daily_sync_time must use HH:MM format."}

        invalid_update_time = client.patch(
            "/api/admin/scenes/scene_00000000000040008000000000009999/git",
            headers=headers,
            json={**scope, "daily_sync_time": "bad"},
        )
        assert invalid_update_time.status_code == 422
        assert invalid_update_time.json() == {"detail": "daily_sync_time must use HH:MM format."}

        invalid_subdir = client.post(
            "/api/admin/scenes/git",
            headers=headers,
            json={
                **scope,
                "name": "Invalid Subdir",
                "git_repository_id": GIT_REPOSITORY_ID,
                "subdir": "../escape",
            },
        )
        assert invalid_subdir.status_code == 422
        assert invalid_subdir.json() == {"detail": "Git subdir is invalid."}
        assert not (storage_root / "tenants/TENANT_ONE/shared/.scenes/Invalid Subdir").exists()

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            invalid_rows = list(
                session.scalars(
                    select(SharedAssetModel).where(
                        SharedAssetModel.kind == "scene",
                        SharedAssetModel.name == "Invalid Subdir",
                    )
                )
            )
            assert invalid_rows == []
    finally:
        engine.dispose()


def test_scene_package_validation_precedes_orphan_directory_conflict(tmp_path: Path) -> None:
    _seed_database(tmp_path)
    storage_root = tmp_path / "vfs"
    orphan = storage_root / "tenants/TENANT_ONE/shared/.scenes/Orphan"
    orphan.mkdir(parents=True)
    (orphan / "keep.md").write_text("keep", encoding="utf-8")
    unsafe = BytesIO()
    with ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape/index.md", "unsafe")
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
            "/api/admin/scenes/package",
            headers={**_super_headers(runtime), "Content-Type": "application/zip"},
            params={
                "scope_type": "tenant",
                "scope_tenant_id": "tenant-1",
                "name": "Orphan",
            },
            content=unsafe.getvalue(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Uploaded Scene package contains unsafe paths."}
    assert (orphan / "keep.md").read_text(encoding="utf-8") == "keep"


def test_scene_file_mutations_cannot_manage_asset_root(tmp_path: Path) -> None:
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
            "/api/admin/scenes",
            headers=headers,
            json={**scope, "name": "Root Boundary"},
        )
        assert created.status_code == 200
        scene_id = created.json()["asset_key"]
        responses = [
            client.put(
                "/api/admin/scenes/file",
                headers=headers,
                json={**scope, "scene_id": scene_id, "path": ".", "content": "x"},
            ),
            client.put(
                "/api/admin/scenes/upload",
                headers={**headers, "Content-Type": "application/octet-stream"},
                params={**scope, "scene_id": scene_id, "path": ""},
                content=b"x",
            ),
            client.put(
                "/api/admin/scenes/directory-package",
                headers={**headers, "Content-Type": "application/zip"},
                params={**scope, "scene_id": scene_id, "path": ""},
                content=b"not-a-package",
            ),
            client.post(
                "/api/admin/scenes/directories",
                headers=headers,
                json={**scope, "scene_id": scene_id, "path": "."},
            ),
            client.post(
                "/api/admin/scenes/move",
                headers=headers,
                json={
                    **scope,
                    "scene_id": scene_id,
                    "src_path": ".",
                    "dst_path": "renamed",
                },
            ),
            client.request(
                "DELETE",
                "/api/admin/scenes/path",
                headers=headers,
                json={**scope, "scene_id": scene_id, "path": ".", "recursive": True},
            ),
        ]

    expected = {"detail": "Scene asset roots are managed by the Scene asset API."}
    assert [response.status_code for response in responses] == [422] * len(responses)
    assert all(response.json() == expected for response in responses)
    assert (storage_root / "tenants/TENANT_ONE/shared/.scenes/Root Boundary").is_dir()


def test_skill_and_scene_requests_reject_unknown_status_and_source(tmp_path: Path) -> None:
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
        payload = {
            "scope_type": "tenant",
            "scope_tenant_id": "tenant-1",
            "name": "invalid",
        }
        responses = [
            client.post(
                "/api/admin/skills",
                headers=headers,
                json={**payload, "status": "active"},
            ),
            client.post(
                "/api/admin/skills",
                headers=headers,
                json={**payload, "source": "git"},
            ),
            client.post(
                "/api/admin/scenes",
                headers=headers,
                json={**payload, "status": "active"},
            ),
            client.post(
                "/api/admin/scenes",
                headers=headers,
                json={**payload, "source": "git"},
            ),
        ]

    assert [response.status_code for response in responses] == [422] * len(responses)
    assert not (storage_root / "tenants/TENANT_ONE/shared/.skills/invalid").exists()
    assert not (storage_root / "tenants/TENANT_ONE/shared/.scenes/invalid").exists()
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(SharedAssetModel).where(
                        SharedAssetModel.kind == "skill",
                        SharedAssetModel.name == "invalid",
                    )
                )
                is None
            )
            assert (
                session.scalar(
                    select(SharedAssetModel).where(
                        SharedAssetModel.kind == "scene",
                        SharedAssetModel.name == "invalid",
                    )
                )
                is None
            )
    finally:
        engine.dispose()


def test_complete_scene_openapi_publishes_git_sync_routes() -> None:
    spec = create_admin_app().openapi()
    paths = {path for path in spec["paths"] if path.startswith("/api/admin/scenes")}
    assert len(paths) == 17
    assert "/api/admin/scenes/{scene_asset_key}/git" in paths
    assert "/api/admin/scenes/{scene_asset_key}/sync" in paths
    assert "/api/admin/scenes/sync-jobs/{job_id}" in paths


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
                        id="team-1",
                        tenant_id="tenant-1",
                        external_key="TEAM",
                        normalized_external_key="TEAM",
                        storage_key="TEAM_ONE",
                        name="Team One",
                        unit_type="team",
                    ),
                    GitRepositoryModel(
                        id=GIT_REPOSITORY_ID,
                        alias="scene-source",
                        display_name="Scene Source",
                        repo_url="https://git.example.invalid/knowledge.git",
                        default_branch="main",
                        status="active",
                    ),
                    GitEntitlementModel(
                        tenant_id="tenant-1",
                        scope_type="tenant",
                        organization_unit_id="",
                        git_repository_id=GIT_REPOSITORY_ID,
                        status="active",
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
        security.issue_admin_token(user_id=ADMIN_ID, username="root", is_super=True)
    )


def _admin_headers(runtime: ZhizhiAdminApiRuntime) -> dict[str, str]:
    security = runtime._iam.identity_security if runtime._iam is not None else None
    assert security is not None
    return _cookie_headers(
        security.issue_admin_token(
            user_id="admin-scene-view",
            username="scene-view",
            is_super=False,
        )
    )


def _cookie_headers(token: str) -> dict[str, str]:
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }


def _seed_scoped_scene_admin(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            permission = session.scalar(
                select(AdminPermissionModel).where(
                    AdminPermissionModel.permission_code == "scenes.view"
                )
            )
            assert permission is not None
            session.add_all(
                [
                    AdminUserModel(
                        id="admin-scene-view",
                        username="scene-view",
                        normalized_username="SCENE-VIEW",
                        password_hash="hash",
                    ),
                    AdminRoleModel(
                        id="role-scene-view",
                        role_code="scene_view_test",
                        role_name="Scene Viewer",
                    ),
                    AdminRolePermissionModel(
                        id="role-scene-view-permission",
                        role_id="role-scene-view",
                        permission_id=permission.id,
                    ),
                    AdminTenantMemberModel(
                        id="scene-view-member",
                        admin_user_id="admin-scene-view",
                        tenant_id="tenant-1",
                        scope_mode="tenant",
                    ),
                    AdminTenantRoleModel(
                        id="scene-view-member-role",
                        tenant_member_id="scene-view-member",
                        role_id="role-scene-view",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_cross_tenant_scene_job(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    TenantModel(
                        id="tenant-2",
                        tenant_code="T2",
                        normalized_tenant_code="T2",
                        tenant_name="Tenant Two",
                        storage_key="TENANT_TWO",
                    ),
                    SharedAssetModel(
                        kind="scene",
                        tenant_id="tenant-2",
                        scope_type="tenant",
                        asset_key="scene-cross-tenant",
                        name="cross-tenant",
                        normalized_name="CROSS-TENANT",
                        source="git",
                        created_by_admin_user_id=ADMIN_ID,
                        updated_by_admin_user_id=ADMIN_ID,
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()
    _seed_background_job(
        project_home,
        job_id="job-cross-tenant",
        job_type="scene_git_sync",
        target_id="scene-cross-tenant",
        payload={"tenant_id": "tenant-2", "scope_type": "tenant", "owner_user_id": None},
    )


def _seed_shared_git_scene(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add(
                SharedAssetModel(
                    kind="scene",
                    tenant_id="tenant-1",
                    scope_type="tenant",
                    asset_key=GIT_SCENE_KEY,
                    name="git-scene",
                    normalized_name="GIT-SCENE",
                    description="Git Scene",
                    status="enabled",
                    source="git",
                    created_by_admin_user_id=ADMIN_ID,
                    updated_by_admin_user_id=ADMIN_ID,
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_background_job(
    project_home: Path,
    *,
    job_id: str,
    job_type: str,
    target_id: str,
    payload: dict[str, object],
) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add(
                BackgroundJobModel(
                    job_id=job_id,
                    job_type=job_type,
                    status="succeeded",
                    target_type="scene",
                    target_id=target_id,
                    payload=payload,
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _scene_package(root: str, files: dict[str, str]) -> bytes:
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        for path, value in files.items():
            archive.writestr(f"{root}/{path}", value)
    return content.getvalue()
