"""Shared workspace adapter contracts."""

from collections.abc import Callable

from gewu_agent_runtime.workspace import WorkspaceBackend
from zhizhi_platform.iam import AccessScope

ScopedBackendFactory = Callable[[AccessScope], WorkspaceBackend]
