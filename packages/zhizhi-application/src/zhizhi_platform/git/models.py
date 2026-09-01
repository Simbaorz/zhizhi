"""Zhizhi managed Git resource models."""

from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from zhizhi_platform.audit import AuditActor


class ManagedGitRepository(BaseModel):
    """One global Git repository configured by a super administrator."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    alias: str = Field(min_length=1)
    display_name: str = ""
    repo_url: str = Field(min_length=1)
    default_branch: str = ""
    username: str = ""
    credential_ciphertext: str = ""
    credential_status: str = "missing"
    status: str = "active"
    last_test_status: str = "untested"
    last_test_message: str = ""
    last_test_time: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedGitEntitlement(BaseModel):
    """Git repository availability granted to one Zhizhi organization scope."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str = Field(pattern="^(tenant|organization_unit)$")
    organization_unit_id: str = ""
    git_repository_id: str = Field(min_length=1)
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GitRepositoryPage(BaseModel):
    """One SQL-filtered global Git repository page."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ManagedGitRepository, ...] = ()
    total: int = Field(default=0, ge=0)


class GitEntitlementPage(BaseModel):
    """One SQL-filtered tenant Git entitlement page."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ManagedGitEntitlement, ...] = ()
    total: int = Field(default=0, ge=0)


class GitCredentials(BaseModel):
    """Credentials supplied to one restricted Git operation."""

    model_config = ConfigDict(frozen=True)

    username: str = ""
    password: str = Field(default="", exclude=True, repr=False)


class GitCheckoutRequest(BaseModel):
    """Input required to prepare one bounded Git content snapshot."""

    model_config = ConfigDict(frozen=True)

    repo_url: str
    credentials: GitCredentials = Field(default_factory=GitCredentials)
    default_branch: str = ""
    branch: str = ""
    ref: str = ""
    subdir: str = ""
    max_content_bytes: int = Field(gt=0)


class GitCheckoutSnapshot(BaseModel):
    """Temporary checked-out content valid for one context-manager scope."""

    model_config = ConfigDict(frozen=True)

    commit_sha: str
    content_path: Path


class WorkspaceSceneGitConfig(BaseModel):
    """Git repository settings for one Zhizhi Scene asset."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str = Field(pattern="^(tenant|user)$")
    owner_user_id: str | None = None
    scene_asset_key: str = Field(min_length=1)
    git_repository_id: str = Field(min_length=1)
    branch: str = ""
    ref: str = ""
    subdir: str = ""
    auto_sync_enabled: bool = False
    daily_sync_time: time | None = None
    timezone: str = "Asia/Shanghai"
    next_sync_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_commit_sha: str = ""
    last_sync_status: str = ""
    last_sync_error: str = ""
    created_by_actor: AuditActor = Field(default_factory=AuditActor.system)
    updated_by_actor: AuditActor = Field(default_factory=AuditActor.system)
    created_at: datetime | None = None
    updated_at: datetime | None = None
