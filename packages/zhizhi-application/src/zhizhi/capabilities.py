"""Read-only Runtime capabilities for Zhizhi."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, SkipValidation

from gewu_agent_runtime.builtins import ask_user_tool, skill
from gewu_agent_runtime.builtins.files import FileToolDescriptionProfile, build_file_tools
from gewu_agent_runtime.tools import Tool, ToolSet
from gewu_agent_runtime.workspace import (
    AccessMode,
    WorkspaceBackend,
    WorkspaceMount,
    WorkspaceSession,
)


class ReadOnlyWorkspaceBackends(BaseModel):
    """Tenant backend followed by root-to-leaf organization backends."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    tenant: SkipValidation[WorkspaceBackend]
    organization: tuple[SkipValidation[WorkspaceBackend], ...] = ()


_FILE_TOOL_DESCRIPTION_PROFILE = FileToolDescriptionProfile(
    relative_root="the default active organization workspace",
    writable_root="no workspace roots",
    read_only_directories_subject="Directories in mounted tenant and organization roots",
    read_only_files="files in mounted tenant or organization roots",
    read_only_files_subject="Files in mounted tenant or organization roots",
    read_only_paths_subject="Mounted tenant and organization paths",
    default_root_name="active organization workspace root",
    glob_absolute_example="/workspace/tenant/**/*.md",
    mounted_path_pattern="/workspace/...",
    list_discovery_guidance=(
        "Use list to discover the read-only tenant and organization roots mounted for this turn."
    ),
)


def build_read_only_workspace(backends: ReadOnlyWorkspaceBackends) -> WorkspaceSession:
    """Expose tenant knowledge plus every ancestor on the active organization path."""

    mounts = [
        WorkspaceMount(
            mount_id="tenant",
            mount_path="/workspace/tenant",
            access_mode=AccessMode.READ_ONLY,
            backend=backends.tenant,
        )
    ]
    for index, backend in enumerate(backends.organization, start=1):
        mounts.append(
            WorkspaceMount(
                mount_id=f"organization-{index}",
                mount_path=f"/workspace/organization-{index}",
                access_mode=AccessMode.READ_ONLY,
                backend=backend,
            )
        )
    default_root = mounts[-1].mount_path
    return WorkspaceSession(tuple(mounts), default_root=default_root)


def build_read_only_tool_set(
    data_source: Tool | None,
    *,
    ask_timeout_seconds: int = 300,
) -> ToolSet:
    """Build the explicit server-safe tool whitelist."""

    if data_source is not None and data_source.name != "query_data_source":
        raise ValueError("data_source must be a bound query_data_source tool")
    file_tools = {tool.name: tool for tool in build_file_tools(_FILE_TOOL_DESCRIPTION_PROFILE)}
    tools = [
        file_tools["list"],
        file_tools["read"],
        file_tools["glob"],
        file_tools["grep"],
        skill,
        ask_user_tool(timeout_seconds=ask_timeout_seconds),
    ]
    if data_source is not None:
        tools.insert(5, data_source)
    return ToolSet(tuple(tools), name="zhizhi-read-only", version="v1")
