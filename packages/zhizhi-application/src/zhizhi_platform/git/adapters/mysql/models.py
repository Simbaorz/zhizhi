"""SQLAlchemy models for managed Git resources and Scene Git references."""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core import new_entity_id
from gewu_core.database import TimezoneAwareDateTime, db_now
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam.adapters.mysql.models import TenantModel


class GitRepositoryModel(ZhizhiBase):
    """Global Git repository resource configured by a super administrator."""

    __tablename__ = "zhizhi_git_repository"
    __table_args__ = (UniqueConstraint("alias", name="uk_git_repository_alias"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    username: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    credential_ciphertext: Mapped[str] = mapped_column(Text, nullable=False, default="")
    credential_status: Mapped[str] = mapped_column(String(16), nullable=False, default="missing")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_test_status: Mapped[str] = mapped_column(String(16), nullable=False, default="untested")
    last_test_message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    last_test_time: Mapped[datetime | None] = mapped_column(TimezoneAwareDateTime(), nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class GitEntitlementModel(ZhizhiBase):
    """Git repository resource granted to one organization scope."""

    __tablename__ = "zhizhi_git_entitlement"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope_type",
            "organization_unit_id",
            "git_repository_id",
            name="uk_git_entitlement_scope_repository",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey(TenantModel.id, ondelete="RESTRICT"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    git_repository_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_git_repository.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class WorkspaceSceneGitConfigModel(ZhizhiBase):
    """Git-backed Scene configuration used for real deletion reference checks."""

    __tablename__ = "zhizhi_workspace_scene_git"
    __table_args__ = (
        UniqueConstraint("scene_asset_key", name="uk_workspace_scene_git_asset"),
        Index("idx_workspace_scene_git_due", "auto_sync_enabled", "next_sync_at"),
        CheckConstraint(
            "(scope_type = 'user' AND owner_user_id IS NOT NULL) OR "
            "(scope_type = 'tenant' AND (owner_user_id IS NULL OR owner_user_id = ''))",
            name="ck_workspace_scene_git_owner_scope",
        ),
        CheckConstraint(
            "(created_by_actor_type = 'system' AND created_by_actor_id IS NULL) OR "
            "(created_by_actor_type = 'admin_user' "
            "AND created_by_actor_id IS NOT NULL)",
            name="ck_workspace_scene_git_created_actor",
        ),
        CheckConstraint(
            "(updated_by_actor_type = 'system' AND updated_by_actor_id IS NULL) OR "
            "(updated_by_actor_type = 'admin_user' "
            "AND updated_by_actor_id IS NOT NULL)",
            name="ck_workspace_scene_git_updated_actor",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scene_asset_key: Mapped[str] = mapped_column(String(64), nullable=False)
    git_repository_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_git_repository.id", ondelete="RESTRICT"), nullable=False
    )
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    ref: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    subdir: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    daily_sync_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    next_sync_at: Mapped[datetime | None] = mapped_column(TimezoneAwareDateTime(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(TimezoneAwareDateTime(), nullable=True)
    last_commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    last_sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    last_sync_error: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    created_by_actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    created_by_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by_actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    updated_by_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )
