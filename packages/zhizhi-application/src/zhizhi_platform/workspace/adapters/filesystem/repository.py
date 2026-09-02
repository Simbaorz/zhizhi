"""Filesystem adapter for administrator-managed 致知 workspaces."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.file_locks import TaskReentrantFileLock
from gewu_core.file_tasks import FileTaskLane, run_file_task
from gewu_core.filesystem import (
    atomic_write_bytes,
    atomic_write_text,
    ensure_monotonic_mtime,
    file_version,
)
from gewu_core.observability import record_filesystem_scan
from zhizhi_platform.iam import AccessScope, AdminScopeRef
from zhizhi_platform.workspace.errors import ConflictError, UnsupportedFileError
from zhizhi_platform.workspace.files import (
    ManagedWorkspacePath,
    ensure_supported_text_file,
)
from zhizhi_platform.workspace.models import ManagedFileEntry, ManagedTextFile
from zhizhi_platform.workspace.storage_paths import (
    ZhizhiWorkspaceStoragePaths,
    access_scope_from_admin_scope,
    normalize_prefix,
    relative_path,
)


class FilesystemManagedWorkspaceRepository:
    """Shared-workspace persistence addressed by 致知 administrative scope."""

    def __init__(
        self,
        storage_root: str | Path,
        max_file_bytes: int = 5 * 1024 * 1024,
        max_skill_package_bytes: int = 50 * 1024 * 1024,
        max_scene_package_bytes: int = 500 * 1024 * 1024,
        max_listing_entries: int = 1000,
    ) -> None:
        self._paths = ZhizhiWorkspaceStoragePaths(storage_root)
        self.storage_root = self._paths.storage_root
        self.max_file_bytes = max_file_bytes
        self.max_skill_package_bytes = max_skill_package_bytes
        self.max_scene_package_bytes = max_scene_package_bytes
        self.max_listing_entries = max_listing_entries
        self._mutation_lock_root = self.storage_root / ".mutation-locks"
        self._mutation_lock_root.mkdir(parents=True, exist_ok=True)
        self._mutation_locks = TaskReentrantFileLock("managed_workspace")

    async def list_entries(
        self,
        scope: AdminScopeRef,
        path: str = "",
        *,
        include_skills: bool,
    ) -> Sequence[ManagedFileEntry]:
        return await run_file_task(
            _list_entries,
            self._paths,
            access_scope_from_admin_scope(scope),
            path,
            include_skills,
            self.max_listing_entries,
            "managed_directory_list",
            lane=FileTaskLane.INTERACTIVE,
        )

    async def read_file(self, scope: AdminScopeRef, path: str) -> ManagedTextFile | None:
        return await run_file_task(
            _read_file,
            self._paths,
            access_scope_from_admin_scope(scope),
            path,
            self.max_file_bytes,
            lane=FileTaskLane.INTERACTIVE,
        )

    async def write_file(
        self,
        scope: AdminScopeRef,
        path: str,
        content: str,
        *,
        expected_version: int | None = None,
    ) -> ManagedTextFile:
        path_obj = ManagedWorkspacePath(value=path)
        content_text = ensure_supported_text_file(
            path_obj,
            content.encode("utf-8"),
            self.max_file_bytes,
        )
        async with self.serialize_mutation(scope):
            return await run_file_task(
                _write_file,
                self._paths,
                access_scope_from_admin_scope(scope),
                path_obj,
                content_text,
                expected_version,
                lane=FileTaskLane.INTERACTIVE,
                wait_on_cancel=True,
            )

    async def resolve_download_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
    ) -> Path | None:
        return await run_file_task(
            _resolve_download_path,
            self._paths,
            access_scope_from_admin_scope(scope),
            path,
            lane=FileTaskLane.INTERACTIVE,
        )

    async def resolve_managed_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
    ) -> Path | None:
        return await run_file_task(
            _resolve_managed_path,
            self._paths,
            access_scope_from_admin_scope(scope),
            path,
            lane=FileTaskLane.INTERACTIVE,
        )

    async def resolve_managed_directory_async(
        self,
        scope: AdminScopeRef,
        path: str,
    ) -> Path | None:
        return await run_file_task(
            _resolve_managed_directory,
            self._paths,
            access_scope_from_admin_scope(scope),
            path,
            lane=FileTaskLane.INTERACTIVE,
        )

    async def replace_file_bytes_async(
        self,
        scope: AdminScopeRef,
        path: str,
        content: bytes,
    ) -> ManagedFileEntry:
        async with self.serialize_mutation(scope):
            return await run_file_task(
                _replace_file_bytes,
                self._paths,
                access_scope_from_admin_scope(scope),
                path,
                content,
                wait_on_cancel=True,
            )

    async def replace_directory_from_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
        source_path: Path,
    ) -> None:
        async with self.serialize_mutation(scope):
            await run_file_task(
                _replace_directory_from_path,
                self._paths,
                access_scope_from_admin_scope(scope),
                path,
                source_path,
                wait_on_cancel=True,
            )

    async def create_directory_async(self, scope: AdminScopeRef, path: str) -> None:
        async with self.serialize_mutation(scope):
            await run_file_task(
                _create_directory,
                self._paths,
                access_scope_from_admin_scope(scope),
                path,
                wait_on_cancel=True,
            )

    async def move_path_async(
        self,
        scope: AdminScopeRef,
        src_path: str,
        dst_path: str,
    ) -> None:
        async with self.serialize_mutation(scope):
            await run_file_task(
                _move_managed_path,
                self._paths,
                access_scope_from_admin_scope(scope),
                src_path,
                dst_path,
                wait_on_cancel=True,
            )

    async def delete_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
        *,
        recursive: bool = False,
    ) -> None:
        async with self.serialize_mutation(scope):
            await run_file_task(
                _delete_managed_path,
                self._paths,
                access_scope_from_admin_scope(scope),
                path,
                recursive,
                wait_on_cancel=True,
            )

    def serialize_mutation(
        self,
        scope: AdminScopeRef,
    ) -> AbstractAsyncContextManager[object]:
        owner_scope = access_scope_from_admin_scope(scope)
        return self._mutation_locks.async_lock(self._mutation_lock_path(owner_scope))

    def _mutation_lock_path(self, owner_scope: AccessScope) -> Path:
        identity = self._paths.scope_root_identity(owner_scope)
        digest = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()
        return self._mutation_lock_root / f"{digest}.lock"


def _modified_at(stat: os.stat_result) -> datetime:
    return datetime.fromtimestamp(stat.st_mtime, UTC)


def _is_special_asset_path(path: str) -> bool:
    parts = [part for part in path.strip("/").split("/") if part]
    return bool(parts and parts[0] in {".skills", ".scenes"})


def _replace_file_bytes(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
    content: bytes,
) -> ManagedFileEntry:
    path_obj = ManagedWorkspacePath(value=path)
    target = paths.file_path(owner_scope, path_obj)
    if target.exists() and not target.is_file():
        raise IsADirectoryError(path)
    previous = file_version(target.stat()) if target.is_file() else 0
    atomic_write_bytes(target, content)
    ensure_monotonic_mtime(target, previous)
    stat = target.stat()
    return ManagedFileEntry(
        entry_type="file",
        name=target.name,
        path=path_obj.value,
        size_bytes=stat.st_size,
        version=file_version(stat),
        modified_at=_modified_at(stat),
    )


def _replace_directory_from_path(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
    source_path: Path,
) -> None:
    target = paths.file_path(owner_scope, ManagedWorkspacePath(value=path))
    target.parent.mkdir(parents=True, exist_ok=True)
    operation_id = uuid4().hex
    replacement = target.parent / f".{target.name}.sync-{operation_id}"
    backup = target.parent / f".{target.name}.backup-{operation_id}"
    try:
        shutil.copytree(source_path, replacement, symlinks=True)
        try:
            if target.exists():
                shutil.move(str(target), str(backup))
            shutil.move(str(replacement), str(target))
            if backup.exists():
                shutil.rmtree(backup)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                shutil.move(str(backup), str(target))
            raise
    finally:
        if replacement.exists():
            shutil.rmtree(replacement)


def _create_directory(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
) -> None:
    paths.file_path(owner_scope, ManagedWorkspacePath(value=path)).mkdir(
        parents=True,
        exist_ok=True,
    )


def _move_managed_path(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    src_path: str,
    dst_path: str,
) -> None:
    source = paths.file_path(owner_scope, ManagedWorkspacePath(value=src_path))
    destination = paths.file_path(owner_scope, ManagedWorkspacePath(value=dst_path))
    if not source.exists():
        raise FileNotFoundError(src_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))


def _delete_managed_path(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
    recursive: bool,
) -> None:
    target = paths.file_path(owner_scope, ManagedWorkspacePath(value=path))
    if not target.exists() and not target.is_symlink():
        raise FileNotFoundError(path)
    if target.is_dir() and not target.is_symlink():
        if not recursive:
            raise IsADirectoryError(path)
        shutil.rmtree(target)
        return
    target.unlink()


def _list_entries(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
    include_skills: bool,
    max_listing_entries: int,
    metric_operation: str,
) -> list[ManagedFileEntry]:
    scanned: list[tuple[os.DirEntry[str], bool, bool]] = []
    outcome = "success"
    try:
        root = paths.scope_root(owner_scope)
        scan_root = paths.existing_prefix(root, normalize_prefix(path))
        if scan_root is None:
            return []
        if scan_root.is_file():
            relative = relative_path(root, scan_root).value
            if _is_special_asset_path(relative) and not include_skills:
                return []
            stat = scan_root.stat()
            return [
                ManagedFileEntry(
                    entry_type="file",
                    name=scan_root.name,
                    path=relative,
                    size_bytes=stat.st_size,
                    version=file_version(stat),
                    modified_at=_modified_at(stat),
                )
            ]
        with os.scandir(scan_root) as entries:
            for entry in entries:
                scanned.append((entry, entry.is_dir(), entry.is_file()))
                if len(scanned) > max_listing_entries:
                    outcome = "capacity_exceeded"
                    raise ApplicationError(
                        ApplicationErrorKind.UNAVAILABLE,
                        f"Workspace listing contains more than {max_listing_entries} entries.",
                    )
        scanned.sort(key=lambda item: (not item[1], item[0].name))
        result: list[ManagedFileEntry] = []
        for entry, is_directory, is_file in scanned:
            relative = Path(entry.path).relative_to(root).as_posix()
            if _is_special_asset_path(relative) and not include_skills:
                continue
            stat = entry.stat()
            if is_directory:
                result.append(
                    ManagedFileEntry(
                        entry_type="directory",
                        name=entry.name,
                        path=relative,
                        modified_at=_modified_at(stat),
                    )
                )
            elif is_file:
                result.append(
                    ManagedFileEntry(
                        entry_type="file",
                        name=entry.name,
                        path=relative,
                        size_bytes=stat.st_size,
                        version=file_version(stat),
                        modified_at=_modified_at(stat),
                    )
                )
        return result
    except BaseException:
        if outcome == "success":
            outcome = "failure"
        raise
    finally:
        record_filesystem_scan(metric_operation, len(scanned), 0, outcome)


def _resolve_download_path(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
) -> Path | None:
    target = paths.file_path(owner_scope, ManagedWorkspacePath(value=path))
    return target if target.is_file() else None


def _resolve_managed_path(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
) -> Path | None:
    target = paths.file_path(owner_scope, ManagedWorkspacePath(value=path))
    return target if target.exists() else None


def _resolve_managed_directory(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
) -> Path | None:
    target = paths.file_path(owner_scope, ManagedWorkspacePath(value=path))
    return target if target.is_dir() else None


def _read_file(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path: str,
    max_file_bytes: int,
) -> ManagedTextFile | None:
    path_obj = ManagedWorkspacePath(value=path)
    target = paths.file_path(owner_scope, path_obj)
    try:
        with target.open("rb") as handle:
            stat = os.fstat(handle.fileno())
            if stat.st_size > max_file_bytes:
                raise UnsupportedFileError(f"Text file exceeds {max_file_bytes} bytes limit.")
            raw = handle.read(max_file_bytes + 1)
    except FileNotFoundError:
        return None
    try:
        content = ensure_supported_text_file(path_obj, raw, max_file_bytes)
    except UnsupportedFileError as exc:
        raise UnsupportedFileError("该文件不支持查看，请下载后打开。") from exc
    return ManagedTextFile(
        path=path_obj.value,
        content=content,
        version=file_version(stat),
        modified_at=_modified_at(stat),
    )


def _write_file(
    paths: ZhizhiWorkspaceStoragePaths,
    owner_scope: AccessScope,
    path_obj: ManagedWorkspacePath,
    content: str,
    expected_version: int | None,
) -> ManagedTextFile:
    target = paths.file_path(owner_scope, path_obj)
    exists = target.is_file()
    current_version = file_version(target.stat()) if exists else 0
    if expected_version is not None and (not exists or current_version != expected_version):
        raise ConflictError("File version does not match expected_version.")
    atomic_write_text(target, content)
    ensure_monotonic_mtime(target, current_version)
    stat = target.stat()
    return ManagedTextFile(
        path=path_obj.value,
        content=content,
        version=file_version(stat),
        modified_at=_modified_at(stat),
    )
