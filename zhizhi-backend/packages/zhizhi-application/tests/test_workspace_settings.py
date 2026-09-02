from pathlib import Path

import pytest

from zhizhi_platform.workspace import resolve_workspace_storage_root


def test_relative_workspace_root_resolves_from_project_home(tmp_path: Path) -> None:
    resolved = resolve_workspace_storage_root("volume/workspace", tmp_path)

    assert resolved == (tmp_path / "volume/workspace").resolve()
    assert resolved.is_absolute()


def test_absolute_workspace_root_is_preserved(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"

    assert resolve_workspace_storage_root(str(workspace_root), tmp_path) == workspace_root.resolve()


def test_empty_workspace_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workspace.storage_root must be configured"):
        resolve_workspace_storage_root("  ", tmp_path)
