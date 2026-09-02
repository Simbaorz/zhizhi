"""One-time browser bootstrap orchestration for the Admin API."""

from __future__ import annotations

import hmac

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gewu_core.http import RsaPasswordTransport
from zhizhi_platform.iam import (
    AdminSeedError,
    InstallationState,
    InstallationStatus,
    SuperAdminBootstrapInput,
    get_installation_status,
    initialize_installation,
)


class AdminBootstrapService:
    """Expose durable setup state and guarded root-account creation."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        password_transport: RsaPasswordTransport,
        bootstrap_token: str,
    ) -> None:
        self._sessions = sessions
        self._password_transport = password_transport
        self._bootstrap_token = bootstrap_token.strip()

    async def status(self) -> InstallationStatus:
        return await get_installation_status(self._sessions)

    def bootstrap_enabled(self, status: InstallationStatus) -> bool:
        return bool(self._bootstrap_token and status.state is InstallationState.SETUP_REQUIRED)

    async def initialize(
        self,
        *,
        bootstrap_token: str,
        username: str,
        display_name: str,
        encrypted_password: str,
    ) -> InstallationStatus:
        status = await self.status()
        if status.state is InstallationState.READY:
            raise AdminSeedError(409, "Zhizhi is already initialized.")
        if status.state is InstallationState.RECOVERY_REQUIRED:
            raise AdminSeedError(409, "Installation recovery is required.")
        if not self._bootstrap_token:
            raise AdminSeedError(503, "Browser bootstrap is not configured.")
        if not hmac.compare_digest(
            self._bootstrap_token.encode("utf-8"),
            bootstrap_token.encode("utf-8"),
        ):
            raise AdminSeedError(403, "Invalid bootstrap token.")
        try:
            password = await self._password_transport.decrypt_async(encrypted_password)
        except ValueError as exc:
            raise AdminSeedError(400, "Invalid encrypted password.") from exc
        await initialize_installation(
            self._sessions,
            SuperAdminBootstrapInput(
                username=username,
                password=password,
                display_name=display_name,
            ),
        )
        return await self.status()
