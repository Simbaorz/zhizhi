"""Secure Zhizhi scope-to-physical Workspace mapping."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gewu_agent_runtime.workspace import LocalWorkspaceBackend, WorkspaceBackend
from zhizhi_platform.errors import PermissionDeniedError
from zhizhi_platform.iam.identity import AccessScope, ScopeType

DEFAULT_MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024
SPECIAL_ASSET_DIR_NAMES = frozenset({".skills", ".scenes"})
SPECIAL_ASSET_TOOL_ACCESS_ERROR = (
    "Modifying special asset files through generic tools is restricted; "
    "use dedicated asset APIs."
)


class WorkspacePath(BaseModel):
    """Normalized relative path confined to one shared workspace root."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value.replace("\\", "/").strip())
        if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
            raise ValueError("Workspace path must be a non-empty relative path.")
        return str(path)


class ZhizhiWorkspaceStoragePaths:
    """Map Zhizhi owner scopes beneath one configured storage root."""

    def __init__(self, storage_root: str | Path) -> None:
        if not str(storage_root):
            raise ValueError("VFS_STORAGE_ROOT is required.")
        root = Path(storage_root).expanduser()
        if not root.is_absolute():
            raise ValueError("VFS_STORAGE_ROOT must be an absolute path.")
        self.storage_root = root

    def scope_root(self, scope: AccessScope) -> Path:
        """Return the confined physical root for one Zhizhi owner scope."""

        root = self.storage_root.resolve()
        candidate = root.joinpath(*self._scope_parts(scope)).resolve()
        self._require_under_root(root, candidate)
        return candidate

    def scope_root_identity(self, scope: AccessScope) -> Path:
        """Return a lexical owner path suitable for stable lock identity derivation."""

        return self.storage_root.joinpath(*self._scope_parts(scope))

    def scoped_path(self, scope: AccessScope, path: WorkspacePath | str) -> Path:
        """Resolve one owner-relative path and reject traversal or symlink escape."""

        relative = path if isinstance(path, WorkspacePath) else WorkspacePath(value=path)
        root = self.scope_root(scope)
        candidate = (root / relative.value).resolve()
        self._require_under_root(root, candidate)
        return candidate

    @staticmethod
    def _scope_parts(scope: AccessScope) -> tuple[str, ...]:
        tenant_key = scope.tenant_storage_key or scope.tenant_id
        if scope.scope_type is ScopeType.TENANT:
            return "tenants", tenant_key, "shared"
        if scope.scope_type is ScopeType.ORGANIZATION_UNIT:
            path = tuple(unit.storage_key or unit.external_key for unit in scope.organization_path)
            return ("tenants", tenant_key, "organization", *path, "shared")
        raise ValueError(f"Unsupported scope type: {scope.scope_type}")

    @staticmethod
    def _require_under_root(root: Path, candidate: Path) -> None:
        if candidate != root and root not in candidate.parents:
            raise PermissionDeniedError("Path escapes mounted workspace root.")


class ZhizhiFilesystemWorkspaceBackendFactory:
    """Create lazy local backends using Zhizhi's exact physical hierarchy."""

    def __init__(
        self,
        storage_root: str | Path,
        *,
        max_file_bytes: int = DEFAULT_MAX_TEXT_FILE_BYTES,
        allow_special_asset_mutations: bool = False,
    ) -> None:
        self.paths = ZhizhiWorkspaceStoragePaths(storage_root)
        self.max_file_bytes = max_file_bytes
        self.allow_special_asset_mutations = allow_special_asset_mutations

    def __call__(self, scope: AccessScope) -> WorkspaceBackend:
        return LocalWorkspaceBackend(
            self.paths.scope_root(scope),
            create_root=False,
            max_file_bytes=self.max_file_bytes,
            protected_directory_names=(
                () if self.allow_special_asset_mutations else SPECIAL_ASSET_DIR_NAMES
            ),
            protected_path_error=SPECIAL_ASSET_TOOL_ACCESS_ERROR,
        )
