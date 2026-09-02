"""Startup-injected encryption for 致知 Data Source credentials."""

from typing import Any

from gewu_core import JsonSecretCipher


class ConfiguredDataSourceCredentialCipher:
    """Resolve the configured key only when a credential operation needs it."""

    def __init__(self, key_material: str) -> None:
        self._key_material = key_material

    def encrypt(self, payload: dict[str, Any]) -> str:
        return self._cipher().encrypt(payload)

    def decrypt(self, ciphertext: str) -> dict[str, Any]:
        return self._cipher().decrypt(ciphertext)

    def _cipher(self) -> JsonSecretCipher:
        if not self._key_material.strip():
            raise RuntimeError("storage_encryption.key must be configured.")
        return JsonSecretCipher(self._key_material)
