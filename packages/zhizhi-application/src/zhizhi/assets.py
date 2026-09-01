"""Subscriber-owned shared Skill and Scene asset index."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, CheckConstraint, Index, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from gewu_core.ids import new_entity_id
from zhizhi.scope import AgentScope
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.workspace.models import WorkspaceSceneAsset

SharedAssetKind = Literal["skill", "scene"]
SharedScopeType = Literal["tenant"]


class SharedAssetModel(ZhizhiBase):
    """Indexed metadata for one Zhizhi shared asset."""

    __tablename__ = "zhizhi_shared_asset"
    __table_args__ = (
        UniqueConstraint("asset_key", name="uk_zhizhi_shared_asset_key"),
        UniqueConstraint(
            "kind",
            "tenant_id",
            "scope_type",
            "normalized_name",
            name="uk_zhizhi_shared_asset_scope_name",
        ),
        Index(
            "idx_zhizhi_shared_asset_visible",
            "kind",
            "tenant_id",
            "status",
        ),
        CheckConstraint("kind IN ('skill', 'scene')", name="ck_zhizhi_shared_asset_kind"),
        CheckConstraint(
            "scope_type = 'tenant'",
            name="ck_zhizhi_shared_asset_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enabled")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    descriptor: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    required_skill_asset_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    recommended_skill_asset_keys: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")
    created_by_admin_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_admin_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class SharedAsset(BaseModel):
    """Transport-neutral shared asset metadata."""

    model_config = ConfigDict(frozen=True)

    asset_key: str = Field(min_length=1, max_length=64)
    kind: SharedAssetKind
    tenant_id: str
    scope_type: SharedScopeType
    name: str
    description: str = ""
    status: Literal["enabled", "disabled", "deleted"] = "enabled"
    content_hash: str = ""
    descriptor: dict[str, Any] = Field(default_factory=dict)
    required_skill_asset_key: str = ""
    recommended_skill_asset_keys: tuple[str, ...] = ()
    source: str = "admin"
    created_by_admin_user_id: str
    updated_by_admin_user_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MysqlSharedAssetRepository:
    """Persist and resolve tenant-wide shared Skill and Scene assets."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_exact(
        self,
        *,
        kind: SharedAssetKind,
        tenant_id: str,
        scope_type: SharedScopeType,
        include_deleted: bool = False,
    ) -> tuple[SharedAsset, ...]:
        model = SharedAssetModel
        statement = select(model).where(
            model.kind == kind,
            model.tenant_id == tenant_id,
            model.scope_type == scope_type,
        )
        if not include_deleted:
            statement = statement.where(model.status != "deleted")
        statement = statement.order_by(model.normalized_name.asc(), model.asset_key.asc())
        async with self._sessions() as session:
            rows = tuple(await session.scalars(statement))
        return tuple(_asset(row) for row in rows)

    async def list_visible(
        self,
        scope: AgentScope,
        *,
        kind: SharedAssetKind,
    ) -> tuple[SharedAsset, ...]:
        model = SharedAssetModel
        statement = (
            select(model)
            .where(
                model.kind == kind,
                model.tenant_id == scope.tenant_id,
                model.status == "enabled",
                model.scope_type == "tenant",
            )
            .order_by(model.normalized_name.asc(), model.asset_key.asc())
        )
        async with self._sessions() as session:
            rows = tuple(await session.scalars(statement))
        return tuple(_asset(row) for row in rows)

    async def get_visible(
        self,
        scope: AgentScope,
        *,
        kind: SharedAssetKind,
        asset_key: str,
    ) -> SharedAsset | None:
        model = SharedAssetModel
        async with self._sessions() as session:
            row = await session.scalar(
                select(model).where(
                    model.kind == kind,
                    model.tenant_id == scope.tenant_id,
                    model.status == "enabled",
                    model.scope_type == "tenant",
                    model.asset_key == asset_key,
                )
            )
        return _asset(row) if row is not None else None  # noqa

    async def get_visible_by_name(
        self,
        scope: AgentScope,
        *,
        kind: SharedAssetKind,
        name: str,
    ) -> SharedAsset | None:
        model = SharedAssetModel
        async with self._sessions() as session:
            row = await session.scalar(
                select(model).where(
                    model.kind == kind,
                    model.tenant_id == scope.tenant_id,
                    model.status == "enabled",
                    model.scope_type == "tenant",
                    model.normalized_name == name.strip().upper(),
                )
            )
        return _asset(row) if row is not None else None  # noqa

    async def get_exact(
        self,
        *,
        kind: SharedAssetKind,
        asset_key: str,
        tenant_id: str,
        scope_type: SharedScopeType,
    ) -> SharedAsset | None:
        model = SharedAssetModel
        async with self._sessions() as session:
            row = await session.scalar(
                select(model).where(
                    model.kind == kind,
                    model.asset_key == asset_key,
                    model.tenant_id == tenant_id,
                    model.scope_type == scope_type,
                    model.status != "deleted",
                )
            )
        return _asset(row) if row is not None else None  # noqa

    async def save(self, asset: SharedAsset) -> SharedAsset:
        async with self._sessions() as session:
            async with session.begin():
                row = await session.scalar(
                    select(SharedAssetModel).where(SharedAssetModel.asset_key == asset.asset_key)
                )
                if row is None:
                    row = SharedAssetModel(asset_key=asset.asset_key)
                    session.add(row)
                _apply(row, asset)
            await session.refresh(row)
        return _asset(row)


class MysqlSharedSceneAssetRepository:
    """Expose tenant Scene Git assets through the shared runtime/admin index."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._assets = MysqlSharedAssetRepository(sessions)

    async def save_scene(self, asset: WorkspaceSceneAsset) -> WorkspaceSceneAsset:
        _require_tenant_scene_scope(asset.scope_type, asset.owner_user_id)
        current = await self._assets.get_exact(
            kind="scene",
            asset_key=asset.asset_key,
            tenant_id=asset.tenant_id,
            scope_type="tenant",
        )
        created_by = asset.created_by_actor.actor_id
        updated_by = _human_actor_id(asset.updated_by_actor)
        if current is None and created_by is None:
            raise ValueError("A new shared Scene must be created by an administrator.")
        saved = await self._assets.save(
            SharedAsset(
                asset_key=asset.asset_key,
                kind="scene",
                tenant_id=asset.tenant_id,
                scope_type="tenant",
                name=asset.name,
                description=asset.description,
                status=asset.status,  # type: ignore[arg-type]
                required_skill_asset_key=asset.required_skill_asset_key,
                recommended_skill_asset_keys=asset.recommended_skill_asset_keys,
                source=asset.source,
                created_by_admin_user_id=(
                    current.created_by_admin_user_id
                    if current is not None
                    else _required_actor_id(created_by)
                ),
                updated_by_admin_user_id=(
                    updated_by
                    or (
                        current.updated_by_admin_user_id
                        if current is not None
                        else _required_actor_id(created_by)
                    )
                ),
            )
        )
        return _workspace_scene_asset(saved)

    async def scene_name_exists(
        self,
        tenant_id: str,
        *,
        scope_type: str,
        owner_user_id: str | None,
        name: str,
        exclude_asset_key: str = "",
    ) -> bool:
        _require_tenant_scene_scope(scope_type, owner_user_id)
        normalized = name.strip().upper()
        return any(
            asset.name.strip().upper() == normalized and asset.asset_key != exclude_asset_key
            for asset in await self._assets.list_exact(
                kind="scene",
                tenant_id=tenant_id,
                scope_type="tenant",
            )
        )

    async def get_scene(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        asset_key: str,
    ) -> WorkspaceSceneAsset | None:
        _require_tenant_scene_scope(scope_type, owner_user_id)
        asset = await self._assets.get_exact(
            kind="scene",
            asset_key=asset_key,
            tenant_id=tenant_id,
            scope_type="tenant",
        )
        return None if asset is None else _workspace_scene_asset(asset)

    async def mark_scene_deleted(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        asset_key: str,
        updated_by_actor: AuditActor,
    ) -> bool:
        current = await self.get_scene(
            tenant_id=tenant_id,
            scope_type=scope_type,
            owner_user_id=owner_user_id,
            asset_key=asset_key,
        )
        if current is None:
            return False
        await self.save_scene(
            current.model_copy(update={"status": "deleted", "updated_by_actor": updated_by_actor})
        )
        return True


def _require_tenant_scene_scope(scope_type: str, owner_user_id: str | None) -> None:
    if scope_type != "tenant" or owner_user_id:
        raise ValueError("Scene Git shared assets only support tenant scope.")


def _human_actor_id(actor: AuditActor) -> str | None:
    return actor.actor_id


def _required_actor_id(actor_id: str | None) -> str:
    if actor_id is None:
        raise ValueError("A shared asset administrator identity is required.")
    return actor_id


def _workspace_scene_asset(asset: SharedAsset) -> WorkspaceSceneAsset:
    return WorkspaceSceneAsset(
        tenant_id=asset.tenant_id,
        scope_type=asset.scope_type,
        asset_key=asset.asset_key,
        name=asset.name,
        description=asset.description,
        status=asset.status,
        required_skill_asset_key=asset.required_skill_asset_key,
        recommended_skill_asset_keys=asset.recommended_skill_asset_keys,
        source=asset.source,
        created_by_actor=AuditActor.admin_user(asset.created_by_admin_user_id),
        updated_by_actor=AuditActor.admin_user(asset.updated_by_admin_user_id),
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _asset(row: SharedAssetModel) -> SharedAsset:
    return SharedAsset(
        asset_key=row.asset_key,
        kind=row.kind,  # type: ignore[arg-type]
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,  # type: ignore[arg-type]
        name=row.name,
        description=row.description,
        status=row.status,  # type: ignore[arg-type]
        content_hash=row.content_hash,
        descriptor=dict(row.descriptor),
        required_skill_asset_key=row.required_skill_asset_key,
        recommended_skill_asset_keys=tuple(row.recommended_skill_asset_keys),
        source=row.source,
        created_by_admin_user_id=row.created_by_admin_user_id,
        updated_by_admin_user_id=row.updated_by_admin_user_id,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _apply(row: SharedAssetModel, asset: SharedAsset) -> None:
    row.kind = asset.kind
    row.tenant_id = asset.tenant_id
    row.scope_type = asset.scope_type
    row.name = asset.name
    row.normalized_name = asset.name.strip().upper()
    row.description = asset.description
    row.status = asset.status
    row.content_hash = asset.content_hash
    row.descriptor = dict(asset.descriptor)
    row.required_skill_asset_key = asset.required_skill_asset_key
    row.recommended_skill_asset_keys = list(asset.recommended_skill_asset_keys)
    row.source = asset.source
    row.created_by_admin_user_id = asset.created_by_admin_user_id
    row.updated_by_admin_user_id = asset.updated_by_admin_user_id
