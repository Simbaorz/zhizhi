import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import (
    ADMIN_PERMISSION_SEEDS,
    AdminSeedError,
    InstallationState,
    SuperAdminBootstrapInput,
    get_installation_status,
    initialize_installation,
    verify_password,
)
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminUserModel,
    InstallationModel,
)


async def _database() -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ZhizhiBase.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_fresh_database_requires_setup_and_initializes_once() -> None:
    engine, sessions = await _database()
    try:
        initial = await get_installation_status(sessions)
        assert initial.state is InstallationState.SETUP_REQUIRED

        user = await initialize_installation(
            sessions,
            SuperAdminBootstrapInput(
                username="root",
                password="strong-password",
                display_name="超级管理员",
            ),
        )

        ready = await get_installation_status(sessions)
        assert ready.state is InstallationState.READY
        assert ready.super_admin_user_id == user.id
        async with sessions() as session:
            installation = await session.get(InstallationModel, 1)
            permissions = list(await session.scalars(select(AdminPermissionModel)))
            stored_user = await session.get(AdminUserModel, user.id)
        assert installation is not None
        assert installation.super_admin_user_id == user.id
        assert len(permissions) == len(ADMIN_PERMISSION_SEEDS)
        assert stored_user is not None
        assert verify_password("strong-password", stored_user.password_hash)

        with pytest.raises(AdminSeedError) as error:
            await initialize_installation(
                sessions,
                SuperAdminBootstrapInput(
                    username="other",
                    password="another-strong-password",
                ),
            )
        assert error.value.status_code == 409
    finally:
        await engine.dispose()


async def test_existing_super_admin_without_installation_record_requires_recovery() -> None:
    engine, sessions = await _database()
    try:
        async with sessions() as session:
            session.add(
                AdminUserModel(
                    username="root",
                    normalized_username="ROOT",
                    password_hash="hash",
                    display_name="Root",
                    status="active",
                    is_super=True,
                )
            )
            await session.commit()

        status = await get_installation_status(sessions)

        assert status.state is InstallationState.RECOVERY_REQUIRED
    finally:
        await engine.dispose()


async def test_initialized_but_disabled_super_admin_requires_recovery() -> None:
    engine, sessions = await _database()
    try:
        user = await initialize_installation(
            sessions,
            SuperAdminBootstrapInput(
                username="root",
                password="strong-password",
            ),
        )
        async with sessions() as session:
            await session.execute(
                update(AdminUserModel).where(AdminUserModel.id == user.id).values(status="disabled")
            )
            await session.commit()

        status = await get_installation_status(sessions)

        assert status.state is InstallationState.RECOVERY_REQUIRED
    finally:
        await engine.dispose()


async def test_super_admin_password_requires_twelve_characters() -> None:
    engine, sessions = await _database()
    try:
        with pytest.raises(AdminSeedError) as error:
            await initialize_installation(
                sessions,
                SuperAdminBootstrapInput(username="root", password="too-short"),
            )

        assert error.value.status_code == 400
        assert "at least 12 characters" in error.value.detail
        assert (await get_installation_status(sessions)).state is InstallationState.SETUP_REQUIRED
    finally:
        await engine.dispose()
