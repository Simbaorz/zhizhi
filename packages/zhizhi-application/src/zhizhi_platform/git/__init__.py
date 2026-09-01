"""Zhizhi-specific managed Git repository package."""

from zhizhi_platform.git.client import (
    RestrictedGitRepositoryClient,
    cleanup_stale_scene_git_workspaces,
)
from zhizhi_platform.git.credentials import ConfiguredGitCredentialCipher
from zhizhi_platform.git.models import (
    GitCheckoutRequest,
    GitCheckoutSnapshot,
    GitCredentials,
    ManagedGitEntitlement,
    ManagedGitRepository,
    WorkspaceSceneGitConfig,
)
from zhizhi_platform.git.ports import GitRepositoryClient, WorkspaceSceneGitRepository
from zhizhi_platform.git.service import ZhizhiGitAdminService
from zhizhi_platform.git.settings import ZhizhiGitSettings

__all__ = [
    "ConfiguredGitCredentialCipher",
    "ZhizhiGitAdminService",
    "ZhizhiGitSettings",
    "GitCheckoutRequest",
    "GitCheckoutSnapshot",
    "GitCredentials",
    "GitRepositoryClient",
    "ManagedGitEntitlement",
    "ManagedGitRepository",
    "RestrictedGitRepositoryClient",
    "WorkspaceSceneGitConfig",
    "WorkspaceSceneGitRepository",
    "cleanup_stale_scene_git_workspaces",
]
