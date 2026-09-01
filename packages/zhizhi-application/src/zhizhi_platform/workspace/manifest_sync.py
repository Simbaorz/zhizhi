"""Synchronize validated SKILL.md metadata with Zhizhi Skill assets."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from gewu_agent_runtime.skill_contracts import ParsedSkillManifest, parse_skill_manifest
from gewu_core.ids import new_uuid4_id
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.workspace.models import (
    WorkspaceAssetRepository,
    WorkspaceSkillAsset,
)

SKILL_ROOT = ".skills"
SKILL_MAIN_FILE = "SKILL.md"


def skill_name_from_main_path(path: str) -> str | None:
    """Return the Skill name for one canonical `.skills/*/SKILL.md` path."""

    parts = PurePosixPath(path.strip("/")).parts
    if len(parts) != 3 or parts[0] != SKILL_ROOT or parts[2] != SKILL_MAIN_FILE:
        return None
    return parts[1] or None


class SkillManifestSynchronizer:
    """Persist the canonical metadata snapshot for a final SKILL.md."""

    def __init__(self, asset_repository: WorkspaceAssetRepository) -> None:
        self.asset_repository = asset_repository

    @staticmethod
    def prepare(
        content: str,
        *,
        expected_name: str | None = None,
    ) -> ParsedSkillManifest:
        return parse_skill_manifest(content, expected_name=expected_name)

    @classmethod
    def prepare_main_content(
        cls,
        path: str,
        content: str,
    ) -> ParsedSkillManifest | None:
        skill_name = skill_name_from_main_path(path)
        return cls.prepare(content, expected_name=skill_name) if skill_name is not None else None

    @classmethod
    def read_manifest_file(
        cls,
        path: Path,
        *,
        expected_name: str | None = None,
    ) -> ParsedSkillManifest:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Skill file must be valid UTF-8 text") from exc
        except OSError as exc:
            raise ValueError("Skill package must contain readable SKILL.md at its root") from exc
        return cls.prepare(content, expected_name=expected_name)

    async def synchronize(
        self,
        manifest: ParsedSkillManifest,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        actor: AuditActor,
        source: str,
        status: str | None = None,
        current: WorkspaceSkillAsset | None = None,
    ) -> WorkspaceSkillAsset:
        descriptor = manifest.descriptor
        existing = current or await self.asset_repository.get_skill_by_name(
            tenant_id,
            scope_type=scope_type,
            owner_user_id=owner_user_id,
            name=descriptor.name,
            include_deleted=True,
        )
        if existing is None:
            asset = WorkspaceSkillAsset(
                tenant_id=tenant_id,
                scope_type=scope_type,
                owner_user_id=owner_user_id,
                asset_key=f"skill_{new_uuid4_id()}",
                name=descriptor.name,
                description=descriptor.description,
                descriptor=manifest.frontmatter,
                content_hash=manifest.content_hash,
                status=status or "enabled",
                source=source,
                created_by_actor=actor,
                updated_by_actor=actor,
            )
        else:
            asset = existing.model_copy(
                update={
                    "name": descriptor.name,
                    "description": descriptor.description,
                    "descriptor": manifest.frontmatter,
                    "content_hash": manifest.content_hash,
                    "status": status
                    or ("enabled" if existing.status == "deleted" else existing.status),
                    "source": source,
                    "updated_by_actor": actor,
                }
            )
        return await self.asset_repository.save_skill(asset)
