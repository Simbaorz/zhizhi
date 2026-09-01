"""Cross-package organization reference tests for the Admin composition root."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zhizhi_admin_api.organization_references import (
    MysqlOrganizationReferenceQuery,
)
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.git.adapters.mysql.models import (
    GitEntitlementModel,
    GitRepositoryModel,
)
from zhizhi_platform.iam.adapters.mysql import (
    MysqlAdminOrgManageRepository,
)
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminTenantMemberModel,
    AdminTenantScopeModel,
    OrganizationUnitModel,
    TenantModel,
)
from zhizhi_platform.workspace import BackgroundJobModel


async def test_organization_references_only_cover_admin_and_resource_ownership() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ZhizhiBase.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            session.add_all(
                [
                    TenantModel(
                        id="t1",
                        tenant_code="T1",
                        normalized_tenant_code="T1",
                        storage_key="T1",
                    ),
                    OrganizationUnitModel(
                        id="a1",
                        tenant_id="t1",
                        external_key="A1",
                        normalized_external_key="A1",
                        storage_key="A1",
                    ),
                    OrganizationUnitModel(
                        id="a2",
                        tenant_id="t1",
                        parent_id="a1",
                        external_key="A2",
                        normalized_external_key="A2",
                        storage_key="A2",
                    ),
                    GitRepositoryModel(
                        id="git1",
                        alias="main-scenes",
                        display_name="Main Scenes",
                        repo_url="http://git.internal/scenes.git",
                    ),
                    GitEntitlementModel(
                        tenant_id="t1",
                        scope_type="tenant",
                        organization_unit_id="",
                        git_repository_id="git1",
                        status="active",
                    ),
                    AdminTenantMemberModel(
                        id="member1",
                        admin_user_id="admin1",
                        tenant_id="t1",
                        status="active",
                        scope_mode="organization_unit",
                    ),
                    AdminTenantScopeModel(
                        tenant_member_id="member1",
                        scope_type="organization_unit",
                        scope_organization_unit_id="a2",
                    ),
                    BackgroundJobModel(
                        job_id="job1",
                        job_type="scene_git_sync",
                        payload={"tenant_id": "t1"},
                    ),
                ]
            )
            await session.commit()

        repository = MysqlAdminOrgManageRepository(
            sessions,
            MysqlOrganizationReferenceQuery(sessions),
        )
        query_count = 0

        def count_query(*_args: object) -> None:
            nonlocal query_count
            query_count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", count_query)
        tenant_references = await repository.organization_reference_counts(tenant_id="t1")
        area_references = await repository.organization_reference_counts(
            tenant_id="t1",
            organization_unit_id="a2",
        )
        other_tenant_organization_unit_references = await repository.organization_reference_counts(
            tenant_id="t2",
            organization_unit_id="a2",
        )
        removal_references = await repository.organization_unit_removal_reference_counts(
            "t1",
            ("a1",),
        )
        retained_references = await repository.organization_unit_removal_reference_counts(
            "t1",
            ("a1", "a2"),
        )
        event.remove(engine.sync_engine, "before_cursor_execute", count_query)

        assert tenant_references == {
            "admin_members": 1,
            "git_entitlements": 1,
            "background_jobs": 1,
        }
        assert area_references == {"admin_scopes": 1}
        assert other_tenant_organization_unit_references == {}
        assert removal_references == {"admin_scopes": 1}
        assert retained_references == {}
        assert query_count == 5
    finally:
        await engine.dispose()
