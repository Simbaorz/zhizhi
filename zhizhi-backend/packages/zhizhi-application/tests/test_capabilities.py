from __future__ import annotations

import pytest

from gewu_agent_runtime.workspace import (
    InMemoryWorkspaceBackend,
    WorkspacePermissionError,
)
from zhizhi.capabilities import (
    ReadOnlyWorkspaceBackends,
    build_read_only_tool_set,
    build_read_only_workspace,
)


async def _backends() -> ReadOnlyWorkspaceBackends:
    tenant = InMemoryWorkspaceBackend()
    division = InMemoryWorkspaceBackend()
    team = InMemoryWorkspaceBackend()
    await tenant.write_bytes("tenant.md", b"tenant")
    await division.write_bytes("division.md", b"division")
    await team.write_bytes("team.md", b"team")
    return ReadOnlyWorkspaceBackends(
        tenant=tenant,
        organization=(division, team),
    )


async def test_workspace_mounts_tenant_and_active_organization_path_read_only() -> None:
    workspace = build_read_only_workspace(await _backends())

    assert workspace.default_root == "/workspace/organization-2"
    assert workspace.allowed_roots() == (
        "/workspace/organization-1",
        "/workspace/organization-2",
        "/workspace/tenant",
    )
    assert all(mount.access_mode.value == "read_only" for mount in workspace.mounts)
    assert await workspace.read_text("team.md") == "team"
    with pytest.raises(WorkspacePermissionError):
        await workspace.write_text("result.md", "forbidden")


def test_tool_set_is_an_explicit_read_only_whitelist() -> None:
    tool_set = build_read_only_tool_set()
    names = {tool.name for tool in tool_set.all()}

    assert names == {
        "list",
        "read",
        "glob",
        "grep",
        "skill",
        "ask_user",
    }
    assert not names.intersection({"write", "append", "edit", "delete", "bash"})
    assert all(not tool.writes_workspace for tool in tool_set.all())


def test_file_tool_descriptions_match_the_zhizhi_workspace() -> None:
    tools = {
        tool.name: tool
        for tool in build_read_only_tool_set().all()
        if tool.name in {"list", "read", "glob", "grep"}
    }

    assert set(tools) == {"list", "read", "glob", "grep"}
    for tool in (tools["list"], tools["read"], tools["glob"]):
        description = tool.description
        assert "tenant and organization" in description
        assert "/workspace/mounted" not in description

    assert "read-only" in tools["list"].description
    assert "active organization workspace" in tools["read"].description
    assert "/workspace/tenant/**/*.md" in tools["glob"].description
    assert tools["grep"].description.startswith("A powerful search tool")
