from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zhizhi.assets import (
    MysqlSharedAssetRepository,
    MysqlSharedSceneAssetRepository,
    SharedAsset,
)
from zhizhi.scope import AgentScope
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import OrganizationUnitRef
from zhizhi_platform.workspace import WorkspaceSceneAsset


async def test_visible_assets_are_tenant_wide_at_every_organization_depth(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assets.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(ZhizhiBase.metadata.create_all)
    repository = MysqlSharedAssetRepository(async_sessionmaker(engine, expire_on_commit=False))
    base = {
        "kind": "skill",
        "tenant_id": "tenant-1",
        "name": "query",
        "created_by_admin_user_id": "admin-1",
        "updated_by_admin_user_id": "admin-1",
    }
    await repository.save(SharedAsset(asset_key="skill_query", scope_type="tenant", **base))
    await repository.save(
        SharedAsset(
            asset_key="skill_other",
            scope_type="tenant",
            name="other",
            kind="skill",
            tenant_id="tenant-1",
            created_by_admin_user_id="admin-1",
            updated_by_admin_user_id="admin-1",
        )
    )
    scope = AgentScope(
        tenant_id="tenant-1",
        tenant_code="TENANT",
        tenant_storage_key="tenant",
        organization_path=(
            OrganizationUnitRef(
                id="division-1",
                external_key="division-1",
                storage_key="division-1",
                name="Division One",
            ),
        ),
        principal_id="user-1",
    )

    visible = await repository.list_visible(scope, kind="skill")

    assert [(asset.name, asset.asset_key) for asset in visible] == [
        ("other", "skill_other"),
        ("query", "skill_query"),
    ]
    await engine.dispose()


async def test_scene_git_adapter_uses_the_shared_scene_index(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scene-git-assets.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(ZhizhiBase.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = MysqlSharedSceneAssetRepository(sessions)
    actor = AuditActor.admin_user("00000000000040008000000000000003")
    asset = WorkspaceSceneAsset(
        tenant_id="tenant-1",
        scope_type="tenant",
        asset_key="scene_00000000000040008000000000000004",
        name="Git Operations",
        source="git",
        created_by_actor=actor,
        updated_by_actor=actor,
    )

    saved = await repository.save_scene(asset)

    assert saved.asset_key == asset.asset_key
    assert await repository.scene_name_exists(
        "tenant-1",
        scope_type="tenant",
        owner_user_id=None,
        name="git operations",
    )
    assert (
        await repository.get_scene(
            tenant_id="tenant-1",
            scope_type="tenant",
            owner_user_id=None,
            asset_key=asset.asset_key,
        )
    ) == saved
    assert await repository.mark_scene_deleted(
        tenant_id="tenant-1",
        scope_type="tenant",
        owner_user_id=None,
        asset_key=asset.asset_key,
        updated_by_actor=AuditActor.system(),
    )
    assert (
        await repository.get_scene(
            tenant_id="tenant-1",
            scope_type="tenant",
            owner_user_id=None,
            asset_key=asset.asset_key,
        )
        is None
    )
    await engine.dispose()
