"""Zhizhi managed Git repository and entitlement use cases."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from gewu_core import ApplicationError, ApplicationErrorKind, utc_now
from gewu_core.blocking import run_external_task
from zhizhi_platform.git.models import ManagedGitEntitlement, ManagedGitRepository
from zhizhi_platform.git.ports import (
    AdminGitRepository,
    GitCredentialCipher,
    GitOrganizationDirectory,
    GitRepositoryClient,
)
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    ensure_admin_permission,
    ensure_admin_scoped_permission,
    ensure_super_admin,
    has_admin_scoped_permission,
)

ACTIVE_STATUS = "active"
INACTIVE_STATUS = "inactive"
VALID_STATUSES = {ACTIVE_STATUS, INACTIVE_STATUS}
CONFIGURED_CREDENTIAL_STATUS = "configured"
MISSING_CREDENTIAL_STATUS = "missing"
TENANT_SCOPE = "tenant"
DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES = 1_000


class GitRepositoryResultPage(BaseModel):
    """One paged global Git repository response."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, object], ...] = ()
    total: int = Field(default=0, ge=0)


class GitEntitlementResultPage(BaseModel):
    """One paged entitlement response and its display catalogs."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, object], ...] = ()
    repositories: tuple[dict[str, object], ...] = ()
    assignable_repositories: tuple[dict[str, object], ...] = ()
    total: int = Field(default=0, ge=0)


class ZhizhiGitAdminService:
    """Execute Zhizhi management use cases for Git resources and entitlements."""

    def __init__(
        self,
        *,
        repository: AdminGitRepository,
        client: GitRepositoryClient,
        org_repository: GitOrganizationDirectory,
        cipher: GitCredentialCipher,
        max_catalog_entries: int = DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
    ) -> None:
        if max_catalog_entries < 1:
            raise ValueError("max_catalog_entries must be greater than zero")
        self._repository = repository
        self._client = client
        self._org_repository = org_repository
        self._cipher = cipher
        self._max_catalog_entries = max_catalog_entries

    async def list_repositories_for(
        self,
        session_user: AdminSessionUser,
        *,
        search: str,
        status: str,
        page: int,
        page_size: int,
    ) -> GitRepositoryResultPage:
        ensure_super_admin(session_user)
        result = await self._repository.list_repositories_page(
            search=search,
            status=status,
            page=page,
            page_size=page_size,
        )
        return GitRepositoryResultPage(
            items=tuple(_public_repository(row) for row in result.items),
            total=result.total,
        )

    async def create_repository_for(
        self,
        session_user: AdminSessionUser,
        *,
        alias: str,
        display_name: str,
        repo_url: str,
        default_branch: str,
        username: str,
        password: str,
        status: str,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        normalized_alias = _required(alias, "仓库别名不能为空。")
        if await self._repository.get_repository_by_alias(normalized_alias) is not None:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "仓库别名已存在。")
        normalized_url = self._client.validate_url(repo_url)
        credential_values = _credentials(username, password)
        saved = await self._repository.save_repository(
            ManagedGitRepository(
                alias=normalized_alias,
                display_name=display_name.strip() or normalized_alias,
                repo_url=normalized_url,
                default_branch=default_branch.strip(),
                username=username.strip(),
                credential_ciphertext=(
                    self._cipher.encrypt(credential_values) if credential_values else ""
                ),
                credential_status=(
                    CONFIGURED_CREDENTIAL_STATUS if credential_values else MISSING_CREDENTIAL_STATUS
                ),
                status=_status(status),
            )
        )
        return _public_repository(saved)

    async def update_repository_for(
        self,
        session_user: AdminSessionUser,
        repository_id: str,
        *,
        display_name: str | None,
        repo_url: str | None,
        default_branch: str | None,
        status: str | None,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        current = await self._require_repository(repository_id)
        saved = await self._repository.save_repository(
            current.model_copy(
                update={
                    "display_name": (
                        display_name.strip()
                        if display_name is not None and display_name.strip()
                        else current.display_name
                    ),
                    "repo_url": (
                        self._client.validate_url(repo_url)
                        if repo_url is not None
                        else current.repo_url
                    ),
                    "default_branch": (
                        default_branch.strip()
                        if default_branch is not None
                        else current.default_branch
                    ),
                    "status": _status(status) if status is not None else current.status,
                }
            )
        )
        return _public_repository(saved)

    async def delete_repository_for(
        self,
        session_user: AdminSessionUser,
        repository_id: str,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        await self._require_repository(repository_id)
        if await self._repository.repository_in_use(repository_id):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT,
                "仓库资源仍被可用池或 Scene 使用，不能删除。",
            )
        if not await self._repository.delete_repository(repository_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Git 仓库资源不存在。")
        return {"deleted": True}

    async def update_credentials_for(
        self,
        session_user: AdminSessionUser,
        repository_id: str,
        *,
        username: str,
        password: str,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        current = await self._require_repository(repository_id)
        normalized_username = username.strip()
        if password:
            credential_values = _credentials(normalized_username, password)
        elif normalized_username:
            existing = self._decrypt_credentials(current)
            credential_values = {
                "username": normalized_username,
                "password": str(existing.get("password") or ""),
            }
        else:
            credential_values = {}
        saved = await self._repository.save_repository(
            current.model_copy(
                update={
                    "username": normalized_username,
                    "credential_ciphertext": (
                        self._cipher.encrypt(credential_values) if credential_values else ""
                    ),
                    "credential_status": (
                        CONFIGURED_CREDENTIAL_STATUS
                        if credential_values
                        else MISSING_CREDENTIAL_STATUS
                    ),
                }
            )
        )
        return _public_repository(saved)

    async def test_repository_for(
        self,
        session_user: AdminSessionUser,
        repository_id: str,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        current = await self._require_repository(repository_id)
        credential_values = self._decrypt_credentials(current)
        try:
            ref_count = await run_external_task(
                self._client.probe,
                current.repo_url,
                str(credential_values.get("username") or ""),
                str(credential_values.get("password") or ""),
            )
            message = f"连接成功，读取到 {ref_count} 个分支或标签引用。"
            test_status = "succeeded"
        except Exception as exc:  # noqa: BLE001
            message = _safe_test_error(exc, credential_values)
            test_status = "failed"
        saved = await self._repository.save_repository(
            current.model_copy(
                update={
                    "last_test_status": test_status,
                    "last_test_message": message,
                    "last_test_time": utc_now(),
                }
            )
        )
        return {
            "ok": test_status == "succeeded",
            "message": message,
            "repository": _public_repository(saved),
        }

    async def list_entitlements_for(
        self,
        session_user: AdminSessionUser,
        tenant_id: str,
        *,
        search: str,
        status: str,
        page: int,
        page_size: int,
    ) -> GitEntitlementResultPage:
        ensure_admin_permission(session_user, "scene_git.view")
        scope = _tenant_scope(tenant_id)
        ensure_admin_scoped_permission(session_user, "scene_git.view", scope)
        page_result = await self._repository.list_entitlements_page(
            tenant_id=tenant_id,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
        )
        repositories = await self._repository.get_repositories_by_ids(
            tuple(row.git_repository_id for row in page_result.items)
        )
        assignable: Sequence[ManagedGitRepository] = ()
        if has_admin_scoped_permission(
            session_user,
            "scene_git.entitlements.edit",
            scope,
        ):
            assignable = await self._repository.list_assignable_repositories(
                tenant_id,
                limit=self._max_catalog_entries + 1,
            )
        return GitEntitlementResultPage(
            items=tuple(_public_entitlement(row) for row in page_result.items),
            repositories=tuple(_scoped_repository(row) for row in repositories),
            assignable_repositories=tuple(
                _project_complete_catalog(
                    assignable,
                    max_entries=self._max_catalog_entries,
                    capacity_message="Assignable Git repository catalog exceeds the server limit.",
                )
            ),
            total=page_result.total,
        )

    async def create_entitlements_for(
        self,
        session_user: AdminSessionUser,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        git_repository_ids: list[str],
        status: str,
    ) -> list[dict[str, object]]:
        ensure_admin_permission(session_user, "scene_git.entitlements.edit")
        ensure_admin_scoped_permission(
            session_user,
            "scene_git.entitlements.edit",
            _tenant_scope(tenant_id),
        )
        if scope_type != TENANT_SCOPE or organization_unit_id.strip():
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "当前版本仅开放触点级 Git 资源分配。",
            )
        if not git_repository_ids:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "至少选择一个 Git 仓库资源。",
            )
        if len(git_repository_ids) > 20:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "一次最多分配 20 个 Git 仓库资源。",
            )
        if len(set(git_repository_ids)) != len(git_repository_ids):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "不能重复选择同一个 Git 仓库资源。",
            )
        normalized_tenant_id = _required(tenant_id, "触点不能为空。")
        tenant = await self._org_repository.get_tenant(normalized_tenant_id)
        if tenant is None or tenant.status != ACTIVE_STATUS:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "触点不存在或已停用。")
        entitlement_status = _status(status)
        for repository_id in git_repository_ids:
            resource = await self._require_repository(repository_id)
            if entitlement_status == ACTIVE_STATUS and resource.status != ACTIVE_STATUS:
                raise ApplicationError(
                    ApplicationErrorKind.CONFLICT,
                    "停用的 Git 仓库资源不能加入可用池。",
                )
            existing = await self._repository.get_entitlement_by_scope_repository(
                tenant_id=normalized_tenant_id,
                scope_type=TENANT_SCOPE,
                organization_unit_id="",
                git_repository_id=repository_id,
            )
            if existing is not None:
                raise ApplicationError(
                    ApplicationErrorKind.CONFLICT,
                    "触点已经拥有所选 Git 仓库资源。",
                )
        saved = await self._repository.save_entitlements(
            tuple(
                ManagedGitEntitlement(
                    tenant_id=normalized_tenant_id,
                    scope_type=TENANT_SCOPE,
                    organization_unit_id="",
                    git_repository_id=repository_id,
                    status=entitlement_status,
                )
                for repository_id in git_repository_ids
            )
        )
        return [_public_entitlement(row) for row in saved]

    async def update_entitlement_for(
        self,
        session_user: AdminSessionUser,
        entitlement_id: str,
        *,
        status: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scene_git.entitlements.edit")
        current = await self._require_entitlement(entitlement_id)
        ensure_admin_scoped_permission(
            session_user,
            "scene_git.entitlements.edit",
            _tenant_scope(current.tenant_id),
        )
        next_status = _status(status)
        resource = await self._require_repository(current.git_repository_id)
        if next_status == ACTIVE_STATUS and resource.status != ACTIVE_STATUS:
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT,
                "停用的 Git 仓库资源不能启用分配。",
            )
        if (
            current.status == ACTIVE_STATUS
            and next_status == INACTIVE_STATUS
            and await self._repository.entitlement_in_use(entitlement_id)
        ):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT,
                "Git 可用池条目仍被 Scene 使用，不能停用。",
            )
        saved = await self._repository.save_entitlement(
            current.model_copy(update={"status": next_status})
        )
        return _public_entitlement(saved)

    async def delete_entitlement_for(
        self,
        session_user: AdminSessionUser,
        entitlement_id: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scene_git.entitlements.edit")
        current = await self._require_entitlement(entitlement_id)
        ensure_admin_scoped_permission(
            session_user,
            "scene_git.entitlements.edit",
            _tenant_scope(current.tenant_id),
        )
        if await self._repository.entitlement_in_use(entitlement_id):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT,
                "Git 可用池条目仍被 Scene 使用，不能删除。",
            )
        if not await self._repository.delete_entitlement(entitlement_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Git 可用池条目不存在。")
        return {"deleted": True}

    async def list_available_repositories_for(
        self,
        session_user: AdminSessionUser,
        tenant_id: str,
    ) -> list[dict[str, object]]:
        ensure_admin_permission(session_user, "scenes.view")
        ensure_admin_scoped_permission(
            session_user,
            "scenes.view",
            _tenant_scope(tenant_id),
        )
        rows = await self._repository.list_available_repositories(
            tenant_id=tenant_id,
            scope_type=TENANT_SCOPE,
            organization_unit_id="",
            limit=self._max_catalog_entries + 1,
        )
        return _project_complete_catalog(
            rows,
            max_entries=self._max_catalog_entries,
            capacity_message="Available Git repository catalog exceeds the server limit.",
        )

    async def _require_repository(self, repository_id: str) -> ManagedGitRepository:
        resource = await self._repository.get_repository(repository_id)
        if resource is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Git 仓库资源不存在。")
        return resource

    async def _require_entitlement(self, entitlement_id: str) -> ManagedGitEntitlement:
        entitlement = await self._repository.get_entitlement(entitlement_id)
        if (
            entitlement is None
            or entitlement.scope_type != TENANT_SCOPE
            or entitlement.organization_unit_id
        ):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Git 可用池条目不存在。")
        return entitlement

    def _decrypt_credentials(self, repository: ManagedGitRepository) -> dict[str, object]:
        if not repository.credential_ciphertext:
            return {}
        return dict(self._cipher.decrypt(repository.credential_ciphertext))


def _credentials(username: str, password: str) -> dict[str, object]:
    normalized_username = username.strip()
    if not normalized_username and not password:
        return {}
    return {"username": normalized_username, "password": password}


def _public_repository(repository: ManagedGitRepository) -> dict[str, object]:
    payload = repository.model_dump(exclude={"credential_ciphertext"})
    payload["has_credential"] = repository.credential_status == CONFIGURED_CREDENTIAL_STATUS
    return payload


def _scoped_repository(repository: ManagedGitRepository) -> dict[str, object]:
    payload = _public_repository(repository)
    payload["username"] = ""
    return payload


def _public_entitlement(entitlement: ManagedGitEntitlement) -> dict[str, object]:
    return entitlement.model_dump()


def _project_complete_catalog(
    rows: Sequence[ManagedGitRepository],
    *,
    max_entries: int,
    capacity_message: str,
) -> list[dict[str, object]]:
    if len(rows) > max_entries:
        raise ApplicationError(ApplicationErrorKind.UNAVAILABLE, capacity_message)
    return [_scoped_repository(row) for row in rows]


def _safe_test_error(exc: Exception, credential_values: dict[str, object]) -> str:
    message = (
        exc.detail
        if isinstance(exc, ApplicationError)
        else f"Git 仓库连接失败（{exc.__class__.__name__}）。"
    )
    for value in credential_values.values():
        secret = str(value or "")
        if secret:
            message = message.replace(secret, "***")
    return message[:512]


def _required(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, message)
    return normalized


def _status(value: str) -> str:
    if value not in VALID_STATUSES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "状态必须是 active 或 inactive。",
        )
    return value


def _tenant_scope(tenant_id: str) -> AdminScopeRef:
    return AdminScopeRef(
        scope_type=AdminScopeType.TENANT,
        scope_tenant_id=tenant_id,
    )
