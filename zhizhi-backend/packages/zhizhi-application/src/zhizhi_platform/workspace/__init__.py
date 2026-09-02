"""致知-specific Workspace resources independent of Agent Runtime."""

from zhizhi_platform.workspace.adapters.filesystem import (
    FilesystemManagedWorkspaceRepository,
)
from zhizhi_platform.workspace.adapters.mysql import (
    BackgroundJobModel,
    MysqlBackgroundJobRepository,
    MysqlWorkspaceSceneGitRepository,
)
from zhizhi_platform.workspace.background_jobs import (
    BackgroundJob,
    BackgroundJobRepository,
    SceneGitSyncDispatcher,
)
from zhizhi_platform.workspace.contracts import ScopedBackendFactory
from zhizhi_platform.workspace.errors import ConflictError, UnsupportedFileError
from zhizhi_platform.workspace.files import FileVersion, ManagedWorkspacePath
from zhizhi_platform.workspace.models import (
    ManagedFileEntry,
    ManagedTextFile,
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
    WorkspaceSceneAsset,
    WorkspaceSceneAssetRepository,
    WorkspaceSkillAsset,
)
from zhizhi_platform.workspace.settings import (
    ZhizhiWorkspaceSettings,
    resolve_workspace_storage_root,
)

__all__ = [
    "ZhizhiWorkspaceSettings",
    "resolve_workspace_storage_root",
    "BackgroundJob",
    "BackgroundJobModel",
    "BackgroundJobRepository",
    "ConflictError",
    "FileVersion",
    "FilesystemManagedWorkspaceRepository",
    "ManagedFileEntry",
    "ManagedTextFile",
    "ManagedWorkspacePath",
    "ManagedWorkspaceRepository",
    "MysqlBackgroundJobRepository",
    "MysqlWorkspaceSceneGitRepository",
    "SceneGitSyncDispatcher",
    "ScopedBackendFactory",
    "WorkspaceAssetRepository",
    "WorkspaceSceneAsset",
    "WorkspaceSceneAssetRepository",
    "WorkspaceSkillAsset",
    "UnsupportedFileError",
]
