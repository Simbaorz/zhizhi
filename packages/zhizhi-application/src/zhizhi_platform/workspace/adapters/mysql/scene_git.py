"""SQLAlchemy persistence for Zhizhi Scene Git configuration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from gewu_core.database import committed_session
from zhizhi_platform.audit import AuditActor, AuditActorType
from zhizhi_platform.git import WorkspaceSceneGitConfig
from zhizhi_platform.git.adapters.mysql.models import WorkspaceSceneGitConfigModel
from zhizhi_platform.workspace.errors import ConflictError
from zhizhi_platform.workspace.models import WorkspaceSceneAssetRepository

SessionFactory = Callable[[], AsyncSession]


class MysqlWorkspaceSceneGitRepository:
    """Persist Scene Git configuration with its Scene metadata invariant."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        scene_assets: WorkspaceSceneAssetRepository,
    ) -> None:
        self._sessions = session_factory
        self._scene_assets = scene_assets

    async def save_config(self, config: WorkspaceSceneGitConfig) -> WorkspaceSceneGitConfig:
        operation = f"save Git Scene config {config.scene_asset_key}"
        scene = await self._scene_assets.get_scene(
            tenant_id=config.tenant_id,
            scope_type=config.scope_type,
            owner_user_id=config.owner_user_id,
            asset_key=config.scene_asset_key,
        )
        if scene is None or scene.status == "deleted":
            raise ConflictError("Git Scene is unavailable for configuration updates.")
        if scene.source != "git":
            raise ConflictError("Scene is not Git-backed.")
        async with committed_session(self._sessions, operation=operation) as session:
            row = await self._get_row(
                session,
                tenant_id=config.tenant_id,
                scope_type=config.scope_type,
                owner_user_id=config.owner_user_id,
                scene_asset_key=config.scene_asset_key,
            )
            if row is None:
                row = WorkspaceSceneGitConfigModel(
                    tenant_id=config.tenant_id,
                    scope_type=config.scope_type,
                    owner_user_id=config.owner_user_id,
                    scene_asset_key=config.scene_asset_key,
                )
                session.add(row)
            self._apply(row, config)
            await session.flush()
            await session.refresh(row)
            saved = self._row_to_domain(row)
        return saved

    async def get_config(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
    ) -> WorkspaceSceneGitConfig | None:
        async with self._sessions() as session:
            row = await self._get_row(
                session,
                tenant_id=tenant_id,
                scope_type=scope_type,
                owner_user_id=owner_user_id,
                scene_asset_key=scene_asset_key,
            )
        return self._row_to_domain(row) if row is not None else None

    async def list_configs_by_scope(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None = None,
        limit: int | None = None,
    ) -> Sequence[WorkspaceSceneGitConfig]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero")
        statement = (
            select(WorkspaceSceneGitConfigModel)
            .where(
                WorkspaceSceneGitConfigModel.tenant_id == tenant_id,
                WorkspaceSceneGitConfigModel.scope_type == scope_type,
                WorkspaceSceneGitConfigModel.owner_user_id == owner_user_id,
            )
            .order_by(WorkspaceSceneGitConfigModel.update_time.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        async with self._sessions() as session:
            rows = tuple(await session.scalars(statement))
        return tuple(self._row_to_domain(row) for row in rows)

    async def delete_config(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
    ) -> bool:
        async with self._sessions() as session:
            row = await self._get_row(
                session,
                tenant_id=tenant_id,
                scope_type=scope_type,
                owner_user_id=owner_user_id,
                scene_asset_key=scene_asset_key,
            )
            if row is None:
                return False
            await session.execute(
                delete(WorkspaceSceneGitConfigModel).where(
                    WorkspaceSceneGitConfigModel.id == row.id
                )
            )
            await session.commit()
            return True

    async def delete_scene_asset_and_config(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
        updated_by_actor: AuditActor,
    ) -> bool:
        deleted = await self._scene_assets.mark_scene_deleted(
            tenant_id=tenant_id,
            scope_type=scope_type,
            owner_user_id=owner_user_id,
            asset_key=scene_asset_key,
            updated_by_actor=updated_by_actor,
        )
        if not deleted:
            return False
        await self.delete_config(
            tenant_id=tenant_id,
            scope_type=scope_type,
            owner_user_id=owner_user_id,
            scene_asset_key=scene_asset_key,
        )
        return True

    async def list_due_auto_sync_configs(
        self,
        *,
        now: datetime,
        limit: int = 50,
    ) -> Sequence[WorkspaceSceneGitConfig]:
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(WorkspaceSceneGitConfigModel)
                    .where(
                        WorkspaceSceneGitConfigModel.auto_sync_enabled.is_(True),
                        WorkspaceSceneGitConfigModel.next_sync_at.is_not(None),
                        WorkspaceSceneGitConfigModel.next_sync_at <= now,
                    )
                    .order_by(WorkspaceSceneGitConfigModel.next_sync_at.asc())
                    .limit(limit)
                )
            )
        return tuple(self._row_to_domain(row) for row in rows)

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
    ) -> WorkspaceSceneGitConfig | None:
        async with self._sessions() as session:
            row = await self._get_row(
                session,
                tenant_id=tenant_id,
                scope_type=scope_type,
                owner_user_id=owner_user_id,
                scene_asset_key=scene_asset_key,
            )
            if row is None:
                return None
            row.last_sync_status = status
            row.last_sync_error = error
            if commit_sha:
                row.last_commit_sha = commit_sha
            if synced_at is not None:
                row.last_synced_at = synced_at
            if next_sync_at is not None:
                row.next_sync_at = next_sync_at
            if updated_by_actor is not None:
                row.updated_by_actor_type = updated_by_actor.actor_type.value
                row.updated_by_actor_id = updated_by_actor.actor_id
            await session.commit()
            await session.refresh(row)
            return self._row_to_domain(row)

    @staticmethod
    async def _get_row(
        session: AsyncSession,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        scene_asset_key: str,
    ) -> WorkspaceSceneGitConfigModel | None:
        return cast(
            WorkspaceSceneGitConfigModel | None,
            await session.scalar(
                select(WorkspaceSceneGitConfigModel).where(
                    WorkspaceSceneGitConfigModel.tenant_id == tenant_id,
                    WorkspaceSceneGitConfigModel.scope_type == scope_type,
                    WorkspaceSceneGitConfigModel.owner_user_id == owner_user_id,
                    WorkspaceSceneGitConfigModel.scene_asset_key == scene_asset_key,
                )
            ),
        )

    @staticmethod
    def _apply(
        row: WorkspaceSceneGitConfigModel,
        config: WorkspaceSceneGitConfig,
    ) -> None:
        row.git_repository_id = config.git_repository_id
        row.branch = config.branch
        row.ref = config.ref
        row.subdir = config.subdir
        row.auto_sync_enabled = config.auto_sync_enabled
        row.daily_sync_time = config.daily_sync_time
        row.timezone = config.timezone
        row.next_sync_at = config.next_sync_at
        row.last_synced_at = config.last_synced_at
        row.last_commit_sha = config.last_commit_sha
        row.last_sync_status = config.last_sync_status
        row.last_sync_error = config.last_sync_error
        row.created_by_actor_type = config.created_by_actor.actor_type.value
        row.created_by_actor_id = config.created_by_actor.actor_id
        row.updated_by_actor_type = config.updated_by_actor.actor_type.value
        row.updated_by_actor_id = config.updated_by_actor.actor_id

    @staticmethod
    def _row_to_domain(row: WorkspaceSceneGitConfigModel) -> WorkspaceSceneGitConfig:
        return WorkspaceSceneGitConfig(
            id=row.id,
            tenant_id=row.tenant_id,
            scope_type=row.scope_type,
            owner_user_id=row.owner_user_id,
            scene_asset_key=row.scene_asset_key,
            git_repository_id=row.git_repository_id,
            branch=row.branch,
            ref=row.ref,
            subdir=row.subdir,
            auto_sync_enabled=row.auto_sync_enabled,
            daily_sync_time=row.daily_sync_time,
            timezone=row.timezone,
            next_sync_at=row.next_sync_at,
            last_synced_at=row.last_synced_at,
            last_commit_sha=row.last_commit_sha,
            last_sync_status=row.last_sync_status,
            last_sync_error=row.last_sync_error,
            created_by_actor=AuditActor(
                actor_type=AuditActorType(row.created_by_actor_type),
                actor_id=row.created_by_actor_id,
            ),
            updated_by_actor=AuditActor(
                actor_type=AuditActorType(row.updated_by_actor_type),
                actor_id=row.updated_by_actor_id,
            ),
            created_at=row.create_time,
            updated_at=row.update_time,
        )
