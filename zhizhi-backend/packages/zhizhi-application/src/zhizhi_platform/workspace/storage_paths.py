"""Secure 致知 scope-to-physical Workspace path mapping."""

from __future__ import annotations

from pathlib import Path

from zhizhi_platform.iam import AccessScope, AdminScopeRef, ScopeType
from zhizhi_platform.iam.errors import PermissionDeniedError
from zhizhi_platform.workspace.files import ManagedWorkspacePath


class ZhizhiWorkspaceStoragePaths:
    """Map 致知 owner scopes to paths beneath one configured storage root."""

    def __init__(self, storage_root: str | Path) -> None:
        if not str(storage_root):
            raise ValueError("VFS_STORAGE_ROOT is required.")
        root = Path(storage_root).expanduser()
        if not root.is_absolute():
            raise ValueError("VFS_STORAGE_ROOT must be an absolute path.")
        self.storage_root = root

    def scope_root(self, scope: AccessScope) -> Path:
        root = self.storage_root.resolve()
        candidate = root.joinpath(*self._scope_parts(scope)).resolve()
        self._require_under_root(root, candidate)
        return candidate

    def scope_root_identity(self, scope: AccessScope) -> Path:
        return self.storage_root.joinpath(*self._scope_parts(scope))

    def file_path(self, scope: AccessScope, path: ManagedWorkspacePath) -> Path:
        root = self.scope_root(scope)
        candidate = (root / path.value).resolve()
        self._require_under_root(root, candidate)
        return candidate

    def existing_prefix(
        self,
        root: Path,
        path_prefix: ManagedWorkspacePath | None,
    ) -> Path | None:
        if path_prefix is None:
            return root if root.exists() else None
        candidate = (root / path_prefix.value).resolve()
        self._require_under_root(root, candidate)
        return candidate if candidate.exists() else None

    @staticmethod
    def _scope_parts(scope: AccessScope) -> tuple[str, ...]:
        tenant_key = scope.tenant_storage_key or scope.tenant_id
        if scope.scope_type is ScopeType.TENANT:
            return ("tenants", tenant_key, "shared")
        if scope.scope_type is ScopeType.ORGANIZATION_UNIT:
            path = tuple(unit.storage_key or unit.external_key for unit in scope.organization_path)
            return ("tenants", tenant_key, "organization", *path, "shared")
        raise ValueError(f"Unsupported scope type: {scope.scope_type}")

    @staticmethod
    def _require_under_root(root: Path, candidate: Path) -> None:
        if candidate != root and root not in candidate.parents:
            raise PermissionDeniedError("Path escapes mounted workspace root.")


def access_scope_from_admin_scope(scope: AdminScopeRef) -> AccessScope:
    """Convert an administrative shared scope into its storage owner scope."""

    return scope.to_access_scope()


def normalize_prefix(path_prefix: str) -> ManagedWorkspacePath | None:
    normalized = path_prefix.replace("\\", "/").strip().strip("/")
    return ManagedWorkspacePath(value=normalized) if normalized else None


def relative_path(root: Path, file_path: Path) -> ManagedWorkspacePath:
    return ManagedWorkspacePath(value=file_path.relative_to(root).as_posix())
