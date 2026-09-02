"""Typed IAM settings loaded once by each 致知 process composition root."""

from pydantic import Field

from gewu_core import StorageEncryptionSettings
from gewu_core.config import SettingsModel
from zhizhi_platform.security import MIN_SECRET_BYTES, validate_storage_secret


class JwtSettings(SettingsModel):
    """JWT signing and validation settings."""

    sk: str = Field(default="", exclude=True, repr=False)
    leeway_seconds: int = Field(default=300, ge=0)


class LoginThrottleSettings(SettingsModel):
    """Shared administrator login throttling settings."""

    enabled: bool = True
    max_failures: int = Field(default=5, ge=1)
    window_seconds: int = Field(default=300, ge=1)
    lockout_seconds: int = Field(default=900, ge=1)


class IamLimitsSettings(SettingsModel):
    """Hard bounds for complete IAM authorization catalogs."""

    max_admin_session_memberships: int = Field(default=256, ge=1)
    max_admin_authorization_rows: int = Field(default=4096, ge=1)
    max_admin_permission_rows: int = Field(default=16384, ge=1)
    max_organization_directory_rows: int = Field(default=4096, ge=1)


def require_jwt_signing_key(settings: JwtSettings) -> str:
    """Return the configured signing key or fail closed."""

    secret = settings.sk.strip()
    if not secret:
        raise RuntimeError("jwt.sk must be configured.")
    return secret


def validate_security_configuration(
    settings: JwtSettings,
    *,
    enforce_strong_secrets: bool,
    storage_encryption: StorageEncryptionSettings | None = None,
) -> None:
    """Reject weak or reused secrets when the explicit policy is enabled."""

    signing_key = ""
    if enforce_strong_secrets:
        signing_key = require_jwt_signing_key(settings)
        _require_minimum_bytes(signing_key, "jwt.sk")
    if storage_encryption is None or not enforce_strong_secrets:
        return
    validate_storage_secret(
        storage_encryption,
        enforce_strong_secrets=enforce_strong_secrets,
    )
    storage_key = storage_encryption.key.strip()
    if signing_key == storage_key:
        raise RuntimeError("jwt.sk and storage_encryption.key must use different secrets.")


def _require_minimum_bytes(value: str, name: str) -> None:
    if len(value.encode("utf-8")) < MIN_SECRET_BYTES:
        raise RuntimeError(f"{name} must contain at least {MIN_SECRET_BYTES} bytes.")
