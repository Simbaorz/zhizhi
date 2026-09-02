"""Outbound boundaries for 致知 managed Git use cases."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Protocol

from zhizhi_platform.audit import AuditActor
from zhizhi_platform.git.models import (
    GitCheckoutRequest,
    GitCheckoutSnapshot,
    GitEntitlementPage,
    GitRepositoryPage,
    ManagedGitEntitlement,
    ManagedGitRepository,
    WorkspaceSceneGitConfig,
)
from zhizhi_platform.iam.models import ManagedTenant


class GitRepositoryClient(Protocol):
    """Validate and probe restricted Git repository endpoints."""

    def validate_url(self, repo_url: str) -> str: ...

    def probe(self, repo_url: str, username: str = "", password: str = "") -> int: ...

    async def resolve_commit(self, request: GitCheckoutRequest) -> str: ...

    def checkout_snapshot(
        self,
        request: GitCheckoutRequest,
    ) -> AbstractAsyncContextManager[GitCheckoutSnapshot]: ...


class GitCredentialCipher(Protocol):
    """Encrypt and decrypt stored Git credential mappings."""

    def encrypt(self, payload: dict[str, Any]) -> str: ...

    def decrypt(self, ciphertext: str) -> dict[str, Any]: ...


class GitOrganizationDirectory(Protocol):
    """致知 organization reads required by Git entitlement policy."""

    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None: ...


class AdminGitRepository(Protocol):
    """Persistence boundary for global Git resources and availability entries."""

    async def list_repositories_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> GitRepositoryPage: ...

    async def get_repository(self, repository_id: str) -> ManagedGitRepository | None: ...

    async def get_repository_by_alias(self, alias: str) -> ManagedGitRepository | None: ...

    async def save_repository(self, repository: ManagedGitRepository) -> ManagedGitRepository: ...

    async def delete_repository(self, repository_id: str) -> bool: ...

    async def repository_in_use(self, repository_id: str) -> bool: ...

    async def list_entitlements_page(
        self,
        *,
        tenant_id: str,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> GitEntitlementPage: ...

    async def get_repositories_by_ids(
        self, repository_ids: Sequence[str]
    ) -> Sequence[ManagedGitRepository]: ...

    async def list_assignable_repositories(
        self, tenant_id: str, *, limit: int
    ) -> Sequence[ManagedGitRepository]: ...

    async def get_entitlement(self, entitlement_id: str) -> ManagedGitEntitlement | None: ...

    async def get_entitlement_by_scope_repository(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        git_repository_id: str,
    ) -> ManagedGitEntitlement | None: ...

    async def save_entitlements(
        self, entitlements: Sequence[ManagedGitEntitlement]
    ) -> Sequence[ManagedGitEntitlement]: ...

    async def save_entitlement(
        self, entitlement: ManagedGitEntitlement
    ) -> ManagedGitEntitlement: ...

    async def delete_entitlement(self, entitlement_id: str) -> bool: ...

    async def entitlement_in_use(self, entitlement_id: str) -> bool: ...

    async def list_available_repositories(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        limit: int,
    ) -> Sequence[ManagedGitRepository]: ...


class WorkspaceSceneGitRepository(Protocol):
    """Persistence boundary for Git-backed Scene settings."""

    async def save_config(self, config: WorkspaceSceneGitConfig) -> WorkspaceSceneGitConfig: ...

    async def get_config(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
    ) -> WorkspaceSceneGitConfig | None: ...

    async def list_configs_by_scope(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None = None,
        limit: int | None = None,
    ) -> Sequence[WorkspaceSceneGitConfig]: ...

    async def delete_config(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
    ) -> bool: ...

    async def delete_scene_asset_and_config(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
        updated_by_actor: AuditActor,
    ) -> bool: ...

    async def list_due_auto_sync_configs(
        self,
        *,
        now: datetime,
        limit: int = 50,
    ) -> Sequence[WorkspaceSceneGitConfig]: ...

    async def update_sync_result(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
        status: str,
        error: str = "",
        commit_sha: str = "",
        synced_at: datetime | None = None,
        next_sync_at: datetime | None = None,
        updated_by_actor: AuditActor | None = None,
    ) -> WorkspaceSceneGitConfig | None: ...
