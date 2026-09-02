"""致知 application policy for managed Skill ZIP packages."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from gewu_agent_runtime.skill_contracts import (
    ParsedSkillManifest,
    parse_skill_manifest,
    rewrite_skill_manifest_identity,
)
from gewu_core.archive import (
    ArchiveLimitExceededError,
    ArchiveValidationError,
    PackageContent,
    extracted_package,
)
from gewu_core.archive import (
    package_content_size as archive_content_size,
)
from gewu_core.archive import (
    package_content_size_async as archive_content_size_async,
)
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.filesystem import (
    regular_file_size_sum,
    remove_path,
    replace_directory_atomically,
)
from zhizhi_platform.workspace.models import ManagedFileEntry

SKILL_MAIN_FILE = "SKILL.md"


def package_skill_manifest(
    content: PackageContent,
    max_package_bytes: int,
    expected_name: str | None = None,
) -> ParsedSkillManifest:
    """Return a validated root manifest from an uploaded Skill package."""

    try:
        with extracted_package(
            content,
            max_package_bytes,
            temp_prefix="zhizhi-admin-Skill-package-manifest-",
        ) as package:
            main_file = package.source_root / SKILL_MAIN_FILE
            if not main_file.is_file():
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Skill package must contain SKILL.md at its root.",
                )
            if regular_file_size_sum(package.source_root) > max_package_bytes:
                raise ApplicationError(
                    ApplicationErrorKind.PAYLOAD_TOO_LARGE,
                    f"Uploaded Skill package exceeds {max_package_bytes} bytes.",
                )
            try:
                return parse_skill_manifest(
                    main_file.read_text(encoding="utf-8"),
                    expected_name=expected_name,
                )
            except UnicodeDecodeError as exc:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Skill file must be valid UTF-8 text",
                ) from exc
            except OSError as exc:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Skill package must contain readable SKILL.md at its root",
                ) from exc
            except ValueError as exc:
                raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, str(exc)) from exc
    except ArchiveValidationError as exc:
        raise admin_archive_error(exc, "Skill") from exc


def validated_asset_skill_content(
    content: str,
    *,
    name: str,
    description: str,
) -> tuple[str, ParsedSkillManifest]:
    """Write request identity into Skill content and validate the result."""

    try:
        normalized = rewrite_skill_manifest_identity(
            content,
            name=name,
            description=description,
        )
        return normalized, parse_skill_manifest(normalized, expected_name=name)
    except ValueError as exc:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, str(exc)) from exc


def validate_package_content(
    content: PackageContent,
    max_package_bytes: int,
    package_kind: str,
    *,
    require_skill_main_file: bool = False,
) -> None:
    """Validate a package before creating its managed asset directory."""

    try:
        with extracted_package(
            content,
            max_package_bytes,
            temp_prefix=f"zhizhi-admin-{package_kind}-package-check-",
        ) as package:
            if require_skill_main_file and not (package.source_root / SKILL_MAIN_FILE).is_file():
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Skill package must contain SKILL.md at its root.",
                )
            if regular_file_size_sum(package.source_root) > max_package_bytes:
                raise ApplicationError(
                    ApplicationErrorKind.PAYLOAD_TOO_LARGE,
                    f"Uploaded {package_kind} package exceeds {max_package_bytes} bytes.",
                )
    except ArchiveValidationError as exc:
        raise admin_archive_error(exc, package_kind) from exc


def replace_managed_directory_with_package(
    physical_path: Path,
    display_path: str,
    content: PackageContent,
    max_package_bytes: int,
    *,
    require_skill_main_file: bool = False,
    package_kind: str = "Skill",
) -> ManagedFileEntry:
    """Replace a managed directory with a safely extracted Skill package."""

    try:
        with extracted_package(
            content,
            max_package_bytes,
            temp_prefix=f"zhizhi-admin-{package_kind}-package-",
        ) as package:
            if require_skill_main_file and not (package.source_root / SKILL_MAIN_FILE).is_file():
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Skill package must contain SKILL.md at its root.",
                )
            replace_directory_atomically(package.source_root, physical_path)
    except ArchiveValidationError as exc:
        raise admin_archive_error(exc, package_kind) from exc
    return managed_directory_entry(
        physical_path,
        display_path,
        regular_file_size_sum(physical_path),
    )


class PreparedManagedPackage(BaseModel):
    """Validated package copied to a target-adjacent staging directory."""

    model_config = ConfigDict(frozen=True)

    staging_path: Path
    size_bytes: int


def prepare_managed_directory_package(
    physical_path: Path,
    content: PackageContent,
    max_package_bytes: int,
    *,
    require_skill_main_file: bool = False,
    package_kind: str = "Skill",
) -> PreparedManagedPackage:
    """Validate and copy a package to target-adjacent staging."""

    staging = physical_path.with_name(f".{physical_path.name}.staging-{uuid4().hex}")
    try:
        with extracted_package(
            content,
            max_package_bytes,
            temp_prefix=f"zhizhi-admin-{package_kind}-package-",
        ) as package:
            if require_skill_main_file and not (package.source_root / SKILL_MAIN_FILE).is_file():
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Skill package must contain SKILL.md at its root.",
                )
            shutil.copytree(package.source_root, staging)
            return PreparedManagedPackage(
                staging_path=staging,
                size_bytes=package.size_bytes,
            )
    except ArchiveValidationError as exc:
        remove_path(staging)
        raise admin_archive_error(exc, package_kind) from exc
    except BaseException:
        remove_path(staging)
        raise


def managed_directory_entry(
    physical_path: Path,
    display_path: str,
    size_bytes: int,
) -> ManagedFileEntry:
    return ManagedFileEntry(
        entry_type="directory",
        path=display_path,
        name=physical_path.name,
        size_bytes=size_bytes,
        version=0,
        modified_at=datetime.fromtimestamp(physical_path.stat().st_mtime, UTC),
    )


def cleanup_prepared_directory_replacement(
    staging: Path,
    backup: Path | None,
) -> None:
    remove_path(staging)
    if backup is not None:
        remove_path(backup)


async def package_content_size_async(content: PackageContent) -> int:
    try:
        return await archive_content_size_async(content)
    except (OSError, ArchiveValidationError) as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Uploaded package is not readable.",
        ) from exc


def package_content_size(content: PackageContent) -> int:
    try:
        return archive_content_size(content)
    except (OSError, ArchiveValidationError) as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Uploaded package is not readable.",
        ) from exc


def admin_archive_error(
    error: ArchiveValidationError,
    package_kind: str,
) -> ApplicationError:
    kind = (
        ApplicationErrorKind.PAYLOAD_TOO_LARGE
        if isinstance(error, ArchiveLimitExceededError)
        else ApplicationErrorKind.INVALID_INPUT
    )
    return ApplicationError(kind, f"Uploaded {package_kind} package {error}")
