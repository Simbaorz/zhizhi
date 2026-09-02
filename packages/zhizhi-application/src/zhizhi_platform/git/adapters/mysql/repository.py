"""SQLAlchemy persistence for 致知 managed Git resources."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.git.adapters.mysql.models import (
    GitEntitlementModel,
    GitRepositoryModel,
    WorkspaceSceneGitConfigModel,
)
from zhizhi_platform.git.models import (
    GitEntitlementPage,
    GitRepositoryPage,
    ManagedGitEntitlement,
    ManagedGitRepository,
)

SessionFactory = Callable[[], AsyncSession]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MysqlAdminGitRepository:
    """Persist global Git resources and their tenant availability entries."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def list_repositories_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> GitRepositoryPage:
        conditions = []
        if status != "all":
            conditions.append(GitRepositoryModel.status == status)
        keyword = search.strip()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            conditions.append(
                or_(
                    GitRepositoryModel.alias.ilike(pattern, escape="\\"),
                    GitRepositoryModel.display_name.ilike(pattern, escape="\\"),
                    GitRepositoryModel.repo_url.ilike(pattern, escape="\\"),
                )
            )
        async with self._sessions() as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(GitRepositoryModel).where(*conditions)
                )
                or 0
            )
            rows = tuple(
                await session.scalars(
                    select(GitRepositoryModel)
                    .where(*conditions)
                    .order_by(GitRepositoryModel.update_time.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
        return GitRepositoryPage(
            items=tuple(self._repository_to_domain(row) for row in rows),
            total=total,
        )

    async def get_repository(self, repository_id: str) -> ManagedGitRepository | None:
        async with self._sessions() as session:
            row = await session.get(GitRepositoryModel, repository_id)
            return self._repository_to_domain(row) if row is not None else None

    async def get_repository_by_alias(self, alias: str) -> ManagedGitRepository | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(GitRepositoryModel).where(GitRepositoryModel.alias == alias)
            )
            return self._repository_to_domain(row) if row is not None else None

    async def save_repository(self, repository: ManagedGitRepository) -> ManagedGitRepository:
        async with self._sessions() as session:
            row = await session.get(GitRepositoryModel, repository.id) if repository.id else None
            if row is None:
                row = GitRepositoryModel()
                session.add(row)
            self._apply_repository(row, repository)
            await session.commit()
            await session.refresh(row)
            return self._repository_to_domain(row)

    async def delete_repository(self, repository_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(GitRepositoryModel, repository_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def repository_in_use(self, repository_id: str) -> bool:
        async with self._sessions() as session:
            return bool(
                await session.scalar(
                    select(
                        or_(
                            exists().where(GitEntitlementModel.git_repository_id == repository_id),
                            exists().where(
                                WorkspaceSceneGitConfigModel.git_repository_id == repository_id
                            ),
                        )
                    )
                )
            )

    async def list_entitlements_page(
        self,
        *,
        tenant_id: str,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> GitEntitlementPage:
        conditions = [
            GitEntitlementModel.tenant_id == tenant_id,
            GitEntitlementModel.scope_type == "tenant",
            GitEntitlementModel.organization_unit_id == "",
        ]
        if status != "all":
            conditions.append(GitEntitlementModel.status == status)
        keyword = search.strip()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            conditions.append(
                or_(
                    GitRepositoryModel.alias.ilike(pattern, escape="\\"),
                    GitRepositoryModel.display_name.ilike(pattern, escape="\\"),
                    GitRepositoryModel.repo_url.ilike(pattern, escape="\\"),
                )
            )
        joined = (
            select(GitEntitlementModel)
            .join(
                GitRepositoryModel,
                GitRepositoryModel.id == GitEntitlementModel.git_repository_id,
            )
            .where(*conditions)
        )
        async with self._sessions() as session:
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(GitEntitlementModel)
                    .join(
                        GitRepositoryModel,
                        GitRepositoryModel.id == GitEntitlementModel.git_repository_id,
                    )
                    .where(*conditions)
                )
                or 0
            )
            rows = tuple(
                await session.scalars(
                    joined.order_by(GitEntitlementModel.update_time.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
        return GitEntitlementPage(
            items=tuple(self._entitlement_to_domain(row) for row in rows),
            total=total,
        )

    async def get_repositories_by_ids(
        self, repository_ids: Sequence[str]
    ) -> Sequence[ManagedGitRepository]:
        ids = tuple(dict.fromkeys(repository_ids))
        if not ids:
            return ()
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(GitRepositoryModel)
                    .where(GitRepositoryModel.id.in_(ids))
                    .order_by(GitRepositoryModel.update_time.desc())
                )
            )
        return tuple(self._repository_to_domain(row) for row in rows)

    async def list_assignable_repositories(
        self,
        tenant_id: str,
        *,
        limit: int,
    ) -> Sequence[ManagedGitRepository]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        assigned = exists().where(
            GitEntitlementModel.tenant_id == tenant_id,
            GitEntitlementModel.scope_type == "tenant",
            GitEntitlementModel.organization_unit_id == "",
            GitEntitlementModel.git_repository_id == GitRepositoryModel.id,
        )
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(GitRepositoryModel)
                    .where(GitRepositoryModel.status == "active", ~assigned)
                    .order_by(GitRepositoryModel.update_time.desc())
                    .limit(limit)
                )
            )
        return tuple(self._repository_to_domain(row) for row in rows)

    async def get_entitlement(self, entitlement_id: str) -> ManagedGitEntitlement | None:
        async with self._sessions() as session:
            row = await session.get(GitEntitlementModel, entitlement_id)
            return self._entitlement_to_domain(row) if row is not None else None

    async def get_entitlement_by_scope_repository(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        git_repository_id: str,
    ) -> ManagedGitEntitlement | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(GitEntitlementModel).where(
                    GitEntitlementModel.tenant_id == tenant_id,
                    GitEntitlementModel.scope_type == scope_type,
                    GitEntitlementModel.organization_unit_id == organization_unit_id,
                    GitEntitlementModel.git_repository_id == git_repository_id,
                )
            )
            return self._entitlement_to_domain(row) if row is not None else None

    async def save_entitlements(
        self,
        entitlements: Sequence[ManagedGitEntitlement],
    ) -> Sequence[ManagedGitEntitlement]:
        async with self._sessions() as session:
            rows: list[GitEntitlementModel] = []
            for entitlement in entitlements:
                row = GitEntitlementModel()
                self._apply_entitlement(row, entitlement)
                session.add(row)
                rows.append(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return tuple(self._entitlement_to_domain(row) for row in rows)

    async def save_entitlement(
        self,
        entitlement: ManagedGitEntitlement,
    ) -> ManagedGitEntitlement:
        async with self._sessions() as session:
            row = await session.get(GitEntitlementModel, entitlement.id) if entitlement.id else None
            if row is None:
                row = GitEntitlementModel()
                session.add(row)
            self._apply_entitlement(row, entitlement)
            await session.commit()
            await session.refresh(row)
            return self._entitlement_to_domain(row)

    async def delete_entitlement(self, entitlement_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(GitEntitlementModel, entitlement_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def entitlement_in_use(self, entitlement_id: str) -> bool:
        async with self._sessions() as session:
            entitlement = await session.get(GitEntitlementModel, entitlement_id)
            if entitlement is None or entitlement.scope_type != "tenant":
                return False
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            WorkspaceSceneGitConfigModel.tenant_id == entitlement.tenant_id,
                            WorkspaceSceneGitConfigModel.git_repository_id
                            == entitlement.git_repository_id,
                        )
                    )
                )
            )

    async def list_available_repositories(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        limit: int,
    ) -> Sequence[ManagedGitRepository]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(GitRepositoryModel)
                    .join(
                        GitEntitlementModel,
                        GitEntitlementModel.git_repository_id == GitRepositoryModel.id,
                    )
                    .where(
                        GitEntitlementModel.tenant_id == tenant_id,
                        GitEntitlementModel.scope_type == scope_type,
                        GitEntitlementModel.organization_unit_id == organization_unit_id,
                        GitEntitlementModel.status == "active",
                        GitRepositoryModel.status == "active",
                    )
                    .order_by(GitRepositoryModel.display_name.asc())
                    .limit(limit)
                )
            )
        return tuple(self._repository_to_domain(row) for row in rows)

    @staticmethod
    def _apply_repository(
        row: GitRepositoryModel,
        repository: ManagedGitRepository,
    ) -> None:
        row.alias = repository.alias
        row.display_name = repository.display_name
        row.repo_url = repository.repo_url
        row.default_branch = repository.default_branch
        row.username = repository.username
        row.credential_ciphertext = repository.credential_ciphertext
        row.credential_status = repository.credential_status
        row.status = repository.status
        row.last_test_status = repository.last_test_status
        row.last_test_message = repository.last_test_message
        row.last_test_time = repository.last_test_time

    @staticmethod
    def _repository_to_domain(row: GitRepositoryModel) -> ManagedGitRepository:
        return ManagedGitRepository(
            id=row.id,
            alias=row.alias,
            display_name=row.display_name,
            repo_url=row.repo_url,
            default_branch=row.default_branch,
            username=row.username,
            credential_ciphertext=row.credential_ciphertext,
            credential_status=row.credential_status,
            status=row.status,
            last_test_status=row.last_test_status,
            last_test_message=row.last_test_message,
            last_test_time=row.last_test_time,
            created_at=row.create_time,
            updated_at=row.update_time,
        )

    @staticmethod
    def _apply_entitlement(
        row: GitEntitlementModel,
        entitlement: ManagedGitEntitlement,
    ) -> None:
        row.tenant_id = entitlement.tenant_id
        row.scope_type = entitlement.scope_type
        row.organization_unit_id = entitlement.organization_unit_id
        row.git_repository_id = entitlement.git_repository_id
        row.status = entitlement.status

    @staticmethod
    def _entitlement_to_domain(row: GitEntitlementModel) -> ManagedGitEntitlement:
        return ManagedGitEntitlement(
            id=row.id,
            tenant_id=row.tenant_id,
            scope_type=row.scope_type,
            organization_unit_id=row.organization_unit_id,
            git_repository_id=row.git_repository_id,
            status=row.status,
            created_at=row.create_time,
            updated_at=row.update_time,
        )
