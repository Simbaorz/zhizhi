from gewu_core import ApplicationError
from zhizhi_platform.git.client import (
    _remote_ref_patterns,
    _resolved_remote_commit,
)


def test_remote_commit_prefers_branch_over_same_named_tag() -> None:
    branch_sha = "a" * 40
    tag_sha = "b" * 40

    assert _remote_ref_patterns("main") == (
        "refs/heads/main",
        "refs/tags/main",
        "refs/tags/main^{}",
    )
    assert (
        _resolved_remote_commit(
            f"{tag_sha}\trefs/tags/main\n{branch_sha}\trefs/heads/main\n",
            "main",
        )
        == branch_sha
    )


def test_remote_commit_uses_peeled_annotated_tag() -> None:
    tag_object_sha = "a" * 40
    commit_sha = "b" * 40

    assert (
        _resolved_remote_commit(
            f"{tag_object_sha}\trefs/tags/v1\n{commit_sha}\trefs/tags/v1^{{}}\n",
            "v1",
        )
        == commit_sha
    )


def test_remote_commit_rejects_missing_ref() -> None:
    try:
        _resolved_remote_commit("", "missing")
    except ApplicationError as exc:
        assert str(exc) == "Git checkout ref does not exist."
    else:
        raise AssertionError("Expected a missing Git ref to fail")
