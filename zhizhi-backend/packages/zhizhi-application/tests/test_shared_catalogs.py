from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gewu_agent_runtime.builtins import parse_skill_manifest
from gewu_agent_runtime.workspace import InMemoryWorkspaceBackend
from zhizhi.assets import MysqlSharedAssetRepository, SharedAsset
from zhizhi.scope import AgentScope
from zhizhi.shared_catalogs import SharedCatalogs
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import AccessScope, OrganizationUnitRef, ScopeType


async def test_catalogs_load_tenant_assets_for_a_nested_organization_context(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalogs.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(ZhizhiBase.metadata.create_all)
    repository = MysqlSharedAssetRepository(async_sessionmaker(engine, expire_on_commit=False))
    tenant_skill = (
        b"---\nname: query-data\ndescription: Tenant query\n"
        b"when-to-use: Tenant data lookup\n---\n\n# Tenant\n"
    )
    manifest = parse_skill_manifest(tenant_skill.decode("utf-8"))
    common = {
        "tenant_id": "tenant-1",
        "name": "query-data",
        "description": "Tenant query",
        "created_by_admin_user_id": "admin-1",
        "updated_by_admin_user_id": "admin-1",
    }
    await repository.save(
        SharedAsset(
            asset_key="skill_tenant",
            kind="skill",
            scope_type="tenant",
            descriptor=manifest.frontmatter.model_dump(mode="json"),
            content_hash=manifest.content_hash,
            **common,
        )
    )
    await repository.save(
        SharedAsset(
            asset_key="scene_tenant",
            kind="scene",
            scope_type="tenant",
            required_skill_asset_key="skill_tenant",
            **common,
        )
    )
    read_paths: list[str] = []

    class RecordingWorkspaceBackend(InMemoryWorkspaceBackend):
        async def read_bytes(self, path: str) -> bytes:
            read_paths.append(path)
            return await super().read_bytes(path)

    backends = {scope_type: RecordingWorkspaceBackend() for scope_type in ScopeType}

    def backend_factory(access: AccessScope) -> InMemoryWorkspaceBackend:
        return backends[access.scope_type]

    await backends[ScopeType.TENANT].write_bytes(".skills/query-data/SKILL.md", tenant_skill)
    scope = AgentScope(
        tenant_id="tenant-1",
        tenant_code="TENANT",
        tenant_storage_key="tenant",
        organization_path=(
            OrganizationUnitRef(
                id="division-1",
                external_key="division",
                storage_key="division",
                name="Division",
            ),
            OrganizationUnitRef(
                id="team-1",
                external_key="team",
                storage_key="team",
                name="Team",
            ),
        ),
        principal_id="user-1",
        principal_type="user",
    )

    skill_catalog, scene_catalog = await SharedCatalogs(repository, backend_factory).resolve(scope)
    skills = await skill_catalog.list_skills()
    assert read_paths == []
    assert skills[0].content == ""
    assert skills[0].when_to_use == "Tenant data lookup"

    with patch.object(
        repository,
        "list_visible",
        side_effect=AssertionError("get_skill must not list all visible assets"),
    ):
        loaded_by_name = await skill_catalog.get_skill("query-data")
    assert loaded_by_name is not None
    assert loaded_by_name.content == "# Tenant"
    assert read_paths == [".skills/query-data/SKILL.md"]
    read_paths.clear()

    with patch.object(
        repository,
        "list_visible",
        side_effect=AssertionError("get_skill_by_asset_key must not list all visible assets"),
    ):
        loaded_skill = await skill_catalog.get_skill_by_asset_key("skill_tenant")
    assert loaded_skill is not None
    assert loaded_skill.content == "# Tenant"
    assert read_paths == [".skills/query-data/SKILL.md"]

    scene = await scene_catalog.get_scene("scene_tenant")

    assert [(skill.asset_key, skill.description) for skill in skills] == [
        ("skill_tenant", "Tenant query")
    ]
    assert skills[0].base_path == "/workspace/tenant/.skills/query-data"
    assert scene is not None
    assert scene.workspace_path == "/workspace/tenant/.scenes/query-data"
    assert scene.required_skill_asset_key == "skill_tenant"
    await engine.dispose()
