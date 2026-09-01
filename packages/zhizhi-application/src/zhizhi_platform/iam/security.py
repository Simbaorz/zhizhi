"""Configured JWT and password implementation of the IAM security boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from gewu_core.blocking import run_cpu_task
from zhizhi_platform.iam.passwords import hash_password, verify_password
from zhizhi_platform.iam.settings import JwtSettings, require_jwt_signing_key


class DefaultIdentitySecurity:
    """Use one startup-injected signer and Zhizhi's PBKDF2 representation."""

    def __init__(self, settings: JwtSettings) -> None:
        self._settings = settings

    @staticmethod
    def hash_password(password: str) -> str:
        return hash_password(password)

    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        return verify_password(password, stored_hash)

    @staticmethod
    async def hash_password_async(password: str) -> str:
        return await run_cpu_task(hash_password, password)

    @staticmethod
    async def verify_password_async(password: str, stored_hash: str) -> bool:
        return await run_cpu_task(verify_password, password, stored_hash)

    def issue_admin_token(
        self,
        *,
        user_id: str,
        username: str,
        is_super: bool,
        token_version: int = 0,
    ) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": str(user_id),
                "username": username,
                "is_super": is_super,
                "kind": "admin",
                "ver": token_version,
                "iat": now,
                "exp": now + timedelta(seconds=8 * 60 * 60),
            },
            self._signing_key(),
            algorithm="HS256",
        )

    def decode_admin_token(self, token: str) -> dict[str, Any]:
        payload = dict(
            jwt.decode(
                token,
                self._signing_key(),
                algorithms=["HS256"],
                leeway=self._settings.leeway_seconds,
            )
        )
        if payload.get("kind") != "admin":
            raise jwt.InvalidTokenError("Invalid admin token kind.")
        return payload

    def _signing_key(self) -> str:
        return require_jwt_signing_key(self._settings)
