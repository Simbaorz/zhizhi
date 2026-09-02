"""Restricted HTTP(S) Git repository validation and probing."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    asynccontextmanager,
    contextmanager,
)
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

from gewu_core import ApplicationError, ApplicationErrorKind
from gewu_core.blocking import run_external_task
from gewu_core.filesystem import regular_file_size_sum
from gewu_core.runtime_temp import runtime_temp_subdir
from zhizhi_platform.git.models import (
    GitCheckoutRequest,
    GitCheckoutSnapshot,
)

SCENE_GIT_TEMP_PREFIX = "zhizhi-scene-git-sync-"


def cleanup_stale_scene_git_workspaces(*, older_than_seconds: int) -> int:
    """Remove abandoned checkout directories older than the worker hard limit."""

    if older_than_seconds < 1:
        raise ValueError("older_than_seconds must be greater than zero")
    cutoff = time.time() - older_than_seconds
    removed = 0
    for path in runtime_temp_subdir("scene-git").iterdir():
        if not path.name.startswith(SCENE_GIT_TEMP_PREFIX) or path.is_symlink():
            continue
        try:
            modified_at = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if modified_at > cutoff:
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except FileNotFoundError:
            continue
        removed += 1
    return removed


class GitRepositoryTarget(BaseModel):
    """Validated endpoint pinned to the DNS addresses used by Git."""

    model_config = ConfigDict(frozen=True)

    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def validate_git_repository_url(repo_url: str) -> str:
    """Return one normalized HTTP(S) Git repository URL."""

    normalized = repo_url.strip()
    if not normalized:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git repository URL is required.",
        )
    if "\n" in normalized or "\r" in normalized:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git repository URL is invalid.",
        )
    try:
        parts = urlsplit(normalized)
        _ = parts.port
    except ValueError as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git repository URL is invalid.",
        ) from exc
    hostname = (parts.hostname or "").rstrip(".").lower()
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not hostname or not parts.path.strip("/"):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Only HTTP(S) Git repository URLs are allowed.",
        )
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git repository URL must not contain credentials or fragments.",
        )
    return urlunsplit((scheme, parts.netloc.lower(), parts.path, parts.query, ""))


def resolve_git_repository_target(repo_url: str) -> GitRepositoryTarget:
    """Resolve and pin one validated Git endpoint."""

    normalized = validate_git_repository_url(repo_url)
    parts = urlsplit(normalized)
    hostname = parts.hostname or ""
    port = parts.port or (80 if parts.scheme == "http" else 443)
    try:
        address_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git repository host could not be resolved.",
        ) from exc
    addresses = tuple(dict.fromkeys(info[4][0] for info in address_info))
    if not addresses:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git repository host could not be resolved.",
        )
    for address in addresses:
        try:
            ipaddress.ip_address(address)
        except ValueError as exc:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Git repository DNS response is invalid.",
            ) from exc
    return GitRepositoryTarget(
        url=normalized,
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


class RestrictedGitRepositoryClient:
    """Restricted synchronous Git client run by the application's external lane."""

    def __init__(
        self,
        command_timeout_seconds: int = 120,
        max_clone_overhead_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if command_timeout_seconds < 1:
            raise ValueError("command_timeout_seconds must be greater than zero")
        if max_clone_overhead_bytes < 0:
            raise ValueError("max_clone_overhead_bytes must not be negative")
        self._command_timeout_seconds = command_timeout_seconds
        self._max_clone_overhead_bytes = max_clone_overhead_bytes

    @staticmethod
    def validate_url(repo_url: str) -> str:
        return validate_git_repository_url(repo_url)

    def probe(self, repo_url: str, username: str = "", password: str = "") -> int:
        target = resolve_git_repository_target(repo_url)
        authenticated_url = _repository_url_with_credentials(
            target.url,
            username.strip(),
            password,
        )
        output = self._run_git_command(
            [
                "git",
                "-c",
                "http.followRedirects=false",
                "-c",
                f"http.curloptResolve={_curl_resolve_value(target)}",
                "ls-remote",
                "--heads",
                "--tags",
                "--",
                authenticated_url,
            ]
        )
        return len([line for line in output.splitlines() if line.strip()])

    def checkout_snapshot(
        self,
        request: GitCheckoutRequest,
    ) -> AbstractAsyncContextManager[GitCheckoutSnapshot]:
        return self._checkout_snapshot_async(request)

    async def resolve_commit(self, request: GitCheckoutRequest) -> str:
        """Resolve the configured branch or tag without creating a checkout."""

        return await run_external_task(
            self._resolve_commit_sync,
            request,
            wait_on_cancel=True,
        )

    def _resolve_commit_sync(self, request: GitCheckoutRequest) -> str:
        target = resolve_git_repository_target(request.repo_url)
        repo_url = _repository_url_with_credentials(
            target.url,
            request.credentials.username,
            request.credentials.password,
        )
        checkout_ref = request.ref or request.branch or request.default_branch
        output = self._run_git_command(
            [
                "git",
                "-c",
                "http.followRedirects=false",
                "-c",
                f"http.curloptResolve={_curl_resolve_value(target)}",
                "ls-remote",
                "--",
                repo_url,
                *_remote_ref_patterns(checkout_ref),
            ]
        )
        return _resolved_remote_commit(output, checkout_ref)

    @asynccontextmanager
    async def _checkout_snapshot_async(
        self,
        request: GitCheckoutRequest,
    ) -> AsyncIterator[GitCheckoutSnapshot]:
        context = self._checkout_snapshot_sync(request)
        snapshot = await run_external_task(
            context.__enter__,
            cancel_result_cleanup=lambda abandoned: _close_abandoned_git_context(
                context,
                abandoned,
            ),
            wait_on_cancel=True,
        )
        try:
            yield snapshot
        except BaseException as exc:
            suppress_exception = await run_external_task(
                context.__exit__,
                type(exc),
                exc,
                exc.__traceback__,
                wait_on_cancel=True,
            )
            if not suppress_exception:
                raise
        else:
            await run_external_task(
                context.__exit__,
                None,
                None,
                None,
                wait_on_cancel=True,
            )

    @contextmanager
    def _checkout_snapshot_sync(
        self,
        request: GitCheckoutRequest,
    ) -> Iterator[GitCheckoutSnapshot]:
        target = resolve_git_repository_target(request.repo_url)
        repo_url = _repository_url_with_credentials(
            target.url,
            request.credentials.username,
            request.credentials.password,
        )
        with tempfile.TemporaryDirectory(
            prefix=SCENE_GIT_TEMP_PREFIX,
            dir=runtime_temp_subdir("scene-git"),
        ) as temp_dir:
            temp_path = Path(temp_dir)
            clone_path = temp_path / "repo"
            stage_path = temp_path / "stage"
            command = [
                "git",
                "-c",
                "http.followRedirects=false",
                "-c",
                "protocol.file.allow=never",
                "-c",
                f"http.curloptResolve={_curl_resolve_value(target)}",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--no-tags",
                f"--filter=blob:limit={request.max_content_bytes}",
            ]
            checkout_ref = request.ref or request.branch or request.default_branch
            if checkout_ref:
                command.extend(["--branch", checkout_ref])
            command.extend(["--", repo_url, str(clone_path)])
            self._run_git_command(
                command,
                watch_path=clone_path,
                max_bytes=request.max_content_bytes + self._max_clone_overhead_bytes,
            )
            commit_sha = self._run_git_command(
                ["git", "-C", str(clone_path), "rev-parse", "HEAD"]
            ).strip()
            source_root = _snapshot_source_root(clone_path, request.subdir)
            _copy_sanitized_snapshot(source_root, stage_path)
            if regular_file_size_sum(stage_path) > request.max_content_bytes:
                raise ApplicationError(
                    ApplicationErrorKind.PAYLOAD_TOO_LARGE,
                    f"Git Scene content exceeds {request.max_content_bytes} bytes.",
                )
            yield GitCheckoutSnapshot(commit_sha=commit_sha, content_path=stage_path)

    def _run_git_command(
        self,
        command: list[str],
        *,
        watch_path: Path | None = None,
        max_bytes: int | None = None,
    ) -> str:
        environment = {
            **os.environ,
            "GIT_ALLOW_PROTOCOL": "http:https",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
        try:
            with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
                process = subprocess.Popen(
                    command,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env=environment,
                )
                deadline = time.monotonic() + self._command_timeout_seconds
                while process.poll() is None:
                    if watch_path is not None and max_bytes is not None:
                        if _path_storage_size(watch_path) > max_bytes:
                            _stop_process(process)
                            raise ApplicationError(
                                ApplicationErrorKind.PAYLOAD_TOO_LARGE,
                                f"Git clone exceeds {max_bytes} bytes.",
                            )
                    if time.monotonic() >= deadline:
                        _stop_process(process)
                        raise ApplicationError(
                            ApplicationErrorKind.TIMEOUT,
                            "Git command timed out.",
                        )
                    time.sleep(0.05)
                if watch_path is not None and max_bytes is not None:
                    if _path_storage_size(watch_path) > max_bytes:
                        raise ApplicationError(
                            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
                            f"Git clone exceeds {max_bytes} bytes.",
                        )
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read(1_000_000).decode("utf-8", errors="replace")
                stderr = stderr_file.read(1_000_000).decode("utf-8", errors="replace")
        except ApplicationError:
            raise
        except FileNotFoundError as exc:
            raise ApplicationError(
                ApplicationErrorKind.INTERNAL,
                "git executable is not available.",
            ) from exc
        except OSError as exc:
            raise ApplicationError(
                ApplicationErrorKind.INTERNAL,
                "Git command could not be started.",
            ) from exc
        if process.returncode:
            detail = (stderr or stdout or "Git command failed.").strip()
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                _redact_sensitive_git_output(detail),
            )
        return stdout


def _close_abandoned_git_context(
    context: AbstractContextManager[GitCheckoutSnapshot],
    _snapshot: GitCheckoutSnapshot,
) -> None:
    context.__exit__(None, None, None)


def _snapshot_source_root(clone_path: Path, subdir: str) -> Path:
    normalized = str(Path(subdir.replace("\\", "/").strip().strip("/")))
    if normalized in {"", "."}:
        return clone_path
    source_root = (clone_path / normalized).resolve()
    clone_root = clone_path.resolve()
    if source_root != clone_root and clone_root not in source_root.parents:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Scene Git subdir is invalid.")
    if not source_root.is_dir():
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Scene Git subdir does not exist.")
    return source_root


def _remote_ref_patterns(checkout_ref: str) -> tuple[str, ...]:
    if not checkout_ref:
        return ("HEAD",)
    if checkout_ref.startswith("refs/tags/"):
        return checkout_ref, f"{checkout_ref}^{{}}"
    if checkout_ref.startswith("refs/"):
        return (checkout_ref,)
    return (
        f"refs/heads/{checkout_ref}",
        f"refs/tags/{checkout_ref}",
        f"refs/tags/{checkout_ref}^{{}}",
    )


def _resolved_remote_commit(output: str, checkout_ref: str) -> str:
    refs: dict[str, str] = {}
    for line in output.splitlines():
        sha, separator, ref_name = line.partition("\t")
        if separator and re.fullmatch(r"[0-9a-fA-F]{40,64}", sha):
            refs[ref_name] = sha.lower()
    if not checkout_ref:
        commit_sha = refs.get("HEAD", "")
    elif checkout_ref.startswith("refs/tags/"):
        commit_sha = refs.get(f"{checkout_ref}^{{}}") or refs.get(checkout_ref, "")
    elif checkout_ref.startswith("refs/"):
        commit_sha = refs.get(checkout_ref, "")
    else:
        commit_sha = (
            refs.get(f"refs/heads/{checkout_ref}")
            or refs.get(f"refs/tags/{checkout_ref}^{{}}")
            or refs.get(f"refs/tags/{checkout_ref}", "")
        )
    if not commit_sha:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git checkout ref does not exist.",
        )
    return commit_sha


def _copy_sanitized_snapshot(source_root: Path, stage_path: Path) -> None:
    _reject_snapshot_symlinks(source_root)
    shutil.copytree(
        source_root,
        stage_path,
        ignore=shutil.ignore_patterns(".git"),
        symlinks=True,
    )


def _reject_snapshot_symlinks(source_root: Path) -> None:
    if source_root.is_symlink():
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git Scene content cannot contain symbolic links.",
        )
    for directory, directory_names, file_names in os.walk(source_root, followlinks=False):
        directory_path = Path(directory)
        for name in (*directory_names, *file_names):
            if (directory_path / name).is_symlink():
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Git Scene content cannot contain symbolic links.",
                )


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()


def _path_storage_size(root: Path) -> int:
    if not root.exists() and not root.is_symlink():
        return 0
    if root.is_symlink() or root.is_file():
        return root.lstat().st_size
    total = root.lstat().st_size
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in (*directory_names, *file_names):
            try:
                total += (directory_path / name).lstat().st_size
            except FileNotFoundError:
                continue
    return total


def _repository_url_with_credentials(repo_url: str, username: str, password: str) -> str:
    if not username and not password:
        return repo_url
    parts = urlsplit(repo_url)
    escaped_username = quote(username, safe="")
    escaped_password = quote(password, safe="")
    userinfo = escaped_username
    if escaped_password:
        userinfo = f"{userinfo}:{escaped_password}" if userinfo else f":{escaped_password}"
    netloc = f"{userinfo}@{parts.hostname or ''}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _curl_resolve_value(target: GitRepositoryTarget) -> str:
    addresses = ",".join(
        f"[{address}]" if ":" in address else address for address in target.addresses
    )
    return f"{target.hostname}:{target.port}:{addresses}"


def _redact_sensitive_git_output(output: str) -> str:
    flattened = output.replace("\n", " ").strip()
    redacted = re.sub(r"(https?://)([^/\s:@]+(:[^/\s@]*)?@)", r"\1***@", flattened)
    return redacted[:1000]
