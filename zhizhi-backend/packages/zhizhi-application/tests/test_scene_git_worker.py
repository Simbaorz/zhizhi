from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest

from zhizhi_platform.git import (
    GitCheckoutRequest,
    GitCheckoutSnapshot,
    ManagedGitRepository,
    WorkspaceSceneGitConfig,
)
from zhizhi_platform.iam import AdminScopeRef, AdminScopeType
from zhizhi_platform.scene.git_worker import SceneGitWorkerService
from zhizhi_platform.workspace import WorkspaceSceneAsset


class _GitClient:
    def __init__(self, remote_commit: str) -> None:
        self.remote_commit = remote_commit
        self.checkout_count = 0

    async def resolve_commit(self, request: GitCheckoutRequest) -> str:
        return self.remote_commit

    @asynccontextmanager
    async def checkout_snapshot(
        self,
        request: GitCheckoutRequest,
    ) -> AsyncIterator[GitCheckoutSnapshot]:
        self.checkout_count += 1
        yield GitCheckoutSnapshot(
            commit_sha=self.remote_commit,
            content_path=Path("stage"),
        )


class _WorkspaceRepository:
    max_scene_package_bytes = 500 * 1024 * 1024

    def __init__(self, existing_directory: Path | None) -> None:
        self.existing_directory = existing_directory
        self.replace_count = 0

    async def resolve_managed_directory_async(
        self,
        scope: AdminScopeRef,
        path: str,
    ) -> Path | None:
        return self.existing_directory

    @asynccontextmanager
    async def serialize_mutation(self, scope: AdminScopeRef) -> AsyncIterator[None]:
        yield

    async def replace_directory_from_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
        source_path: Path,
    ) -> None:
        self.replace_count += 1


class _JobRepository:
    def __init__(self) -> None:
        self.progress: list[tuple[int, str]] = []

    async def update_progress(
        self,
        job_id: str,
        *,
        progress: int,
        message: str,
    ) -> None:
        self.progress.append((progress, message))


def _service(
    git_client: _GitClient,
    workspace_repository: _WorkspaceRepository,
    job_repository: _JobRepository,
) -> SceneGitWorkerService:
    unused = cast(Any, object())
    return SceneGitWorkerService(
        git_repository=unused,
        git_client=cast(Any, git_client),
        credential_cipher=unused,
        org_repository=unused,
        workspace_repository=cast(Any, workspace_repository),
        asset_repository=unused,
        scene_git_repository=unused,
        job_repository=cast(Any, job_repository),
    )


async def _sync_snapshot(
    *,
    last_commit_sha: str,
    existing_directory: Path | None,
) -> tuple[str, _GitClient, _WorkspaceRepository, _JobRepository]:
    git_client = _GitClient("a" * 40)
    workspace_repository = _WorkspaceRepository(existing_directory)
    job_repository = _JobRepository()
    commit_sha = await _service(
        git_client,
        workspace_repository,
        job_repository,
    )._sync_snapshot(
        WorkspaceSceneAsset(
            tenant_id="tenant-1",
            scope_type="tenant",
            asset_key="scene-1",
            name="git-scene",
            source="git",
        ),
        WorkspaceSceneGitConfig(
            tenant_id="tenant-1",
            scope_type="tenant",
            scene_asset_key="scene-1",
            git_repository_id="repository-1",
            branch="main",
            last_commit_sha=last_commit_sha,
        ),
        ManagedGitRepository(
            alias="repository-1",
            repo_url="https://git.example.com/group/repository.git",
            default_branch="main",
        ),
        AdminScopeRef(
            scope_type=AdminScopeType.TENANT,
            scope_tenant_id="tenant-1",
            scope_tenant_storage_key="tenant-storage-1",
        ),
        "job-1",
    )
    return commit_sha, git_client, workspace_repository, job_repository


@pytest.mark.asyncio
async def test_scene_git_sync_skips_checkout_when_commit_and_directory_are_unchanged(
    tmp_path: Path,
) -> None:
    commit_sha, git_client, workspace_repository, job_repository = await _sync_snapshot(
        last_commit_sha="a" * 40,
        existing_directory=tmp_path / "git-scene",
    )

    assert commit_sha == "a" * 40
    assert git_client.checkout_count == 0
    assert workspace_repository.replace_count == 0
    assert job_repository.progress[-1] == (95, "远端提交未变化，跳过 Scene 内容替换")


@pytest.mark.asyncio
async def test_scene_git_sync_restores_missing_directory_for_unchanged_commit() -> None:
    _commit_sha, git_client, workspace_repository, _job_repository = await _sync_snapshot(
        last_commit_sha="a" * 40,
        existing_directory=None,
    )

    assert git_client.checkout_count == 1
    assert workspace_repository.replace_count == 1
