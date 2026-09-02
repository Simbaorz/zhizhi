"""Explicit secret validation shared by 致知 processes."""

from gewu_core import StorageEncryptionSettings

MIN_SECRET_BYTES = 32


def validate_storage_secret(
    settings: StorageEncryptionSettings,
    *,
    enforce_strong_secrets: bool,
) -> None:
    """Require a strong storage key when the explicit policy is enabled."""

    if not enforce_strong_secrets:
        return
    secret = settings.key.strip()
    if not secret:
        raise RuntimeError("storage_encryption.key must be configured.")
    if len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise RuntimeError(
            f"storage_encryption.key must contain at least {MIN_SECRET_BYTES} bytes."
        )
