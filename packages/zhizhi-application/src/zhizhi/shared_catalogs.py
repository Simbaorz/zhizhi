"""Runtime catalogs backed by 致知 shared assets."""

from __future__ import annotations

from collections.abc import Sequence

from gewu_agent_runtime.builtins import (
    SceneDocument,
    SkillDescriptor,
    SkillDocument,
    SkillFrontmatterSnapshot,
    build_skill_document,
    load_skill_document,
)
from gewu_agent_runtime.workspace import WorkspaceNotFoundError
from gewu_core.file_tasks import FileTaskLane, run_file_task
from zhizhi.assets import MysqlSharedAssetRepository, SharedAsset
from zhizhi.runtime_capabilities import agent_access_scope
from zhizhi.scope import AgentScope
from zhizhi_platform.iam import AccessScope
from zhizhi_platform.workspace import ScopedBackendFactory


class SharedCatalogs:
    """Create per-turn Skill and Scene catalogs from one resolved scope."""

    def __init__(
        self,
        repository: MysqlSharedAssetRepository,
        workspace_backends: ScopedBackendFactory,
    ) -> None:
        self._repository = repository
        self._workspace_backends = workspace_backends

    async def resolve(
        self,
        scope: AgentScope,
    ) -> tuple[SharedSkillCatalog, SharedSceneCatalog]:
        return (
            SharedSkillCatalog(scope, self._repository, self._workspace_backends),
            SharedSceneCatalog(scope, self._repository),
        )


class SharedSkillCatalog:
    def __init__(
        self,
        scope: AgentScope,
        repository: MysqlSharedAssetRepository,
        workspace_backends: ScopedBackendFactory,
    ) -> None:
        self._scope = scope
        self._repository = repository
        self._workspace_backends = workspace_backends

    async def list_skills(self, *, limit: int | None = None) -> Sequence[SkillDocument]:
        assets = await self._repository.list_visible(self._scope, kind="skill")
        if limit is not None:
            assets = assets[:limit]
        return tuple(_skill_descriptor(asset) for asset in assets)

    async def get_skill(self, name: str) -> SkillDocument | None:
        asset = await self._repository.get_visible_by_name(
            self._scope,
            kind="skill",
            name=name,
        )
        return await self._load(asset) if asset is not None else None

    async def get_skill_by_asset_key(self, asset_key: str) -> SkillDocument | None:
        asset = await self._repository.get_visible(
            self._scope,
            kind="skill",
            asset_key=asset_key,
        )
        return await self._load(asset) if asset is not None else None

    async def _load(self, asset: SharedAsset) -> SkillDocument | None:
        source_path = f".skills/{asset.name}/SKILL.md"
        backend = await run_file_task(
            self._workspace_backends,
            _asset_access_scope(self._scope, asset),
            lane=FileTaskLane.INTERACTIVE,
        )
        try:
            raw = await backend.read_bytes(source_path)
        except WorkspaceNotFoundError:
            return None
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        loaded = load_skill_document(
            content,
            expected_name=asset.name,
            asset_key=asset.asset_key,
            base_path=f"{_logical_root(asset.scope_type)}/.skills/{asset.name}",
            source_path=source_path,
        ).skill
        if loaded is None or (asset.content_hash and loaded.content_hash != asset.content_hash):
            return None
        return loaded


class SharedSceneCatalog:
    def __init__(
        self,
        scope: AgentScope,
        repository: MysqlSharedAssetRepository,
    ) -> None:
        self._scope = scope
        self._repository = repository

    async def get_scene(self, asset_key: str) -> SceneDocument | None:
        asset = await self._repository.get_visible(
            self._scope,
            kind="scene",
            asset_key=asset_key,
        )
        if asset is None:
            return None
        return SceneDocument(
            asset_key=asset.asset_key,
            name=asset.name,
            description=asset.description,
            workspace_path=f"{_logical_root(asset.scope_type)}/.scenes/{asset.name}",
            required_skill_asset_key=asset.required_skill_asset_key,
            recommended_skill_asset_keys=asset.recommended_skill_asset_keys,
            metadata=dict(asset.descriptor),
        )


def _asset_access_scope(scope: AgentScope, asset: SharedAsset) -> AccessScope:
    access = agent_access_scope(scope)
    ancestors = {value.scope_type.value: value for value in access.shared_ancestor_scopes()}
    return ancestors[asset.scope_type]


def _skill_descriptor(asset: SharedAsset) -> SkillDocument:
    try:
        descriptor = SkillFrontmatterSnapshot.model_validate(asset.descriptor).to_descriptor()
    except ValueError:
        try:
            descriptor = SkillDescriptor.model_validate(asset.descriptor)
        except ValueError:
            descriptor = SkillDescriptor(name=asset.name, description=asset.description)
    descriptor = descriptor.model_copy(
        update={"name": asset.name, "description": asset.description}
    )
    source_path = f".skills/{asset.name}/SKILL.md"
    return build_skill_document(
        descriptor,
        asset_key=asset.asset_key,
        base_path=f"{_logical_root(asset.scope_type)}/.skills/{asset.name}",
        source_path=source_path,
        content_hash=asset.content_hash,
    )


def _logical_root(scope_type: str) -> str:
    if scope_type != "tenant":
        raise ValueError(f"Unsupported shared-asset scope: {scope_type}")
    return "/workspace/tenant"
