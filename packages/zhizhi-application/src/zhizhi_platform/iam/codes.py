"""Stable validation and normalization used by Zhizhi identities."""

import re
from typing import Any

_STABLE_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def validate_stable_code(
    value: str,
    label: str,
    *,
    min_length: int = 1,
    max_length: int = 64,
) -> str:
    """Validate one filesystem-safe Zhizhi business code."""

    code = value.strip()
    if not (min_length <= len(code) <= max_length):
        raise ValueError(f"{label}长度必须是 {min_length}-{max_length} 个字符。")
    if not _STABLE_CODE_RE.fullmatch(code):
        raise ValueError(
            f"{label}只能以英文字母或数字开头，并且只能包含英文字母、数字、下划线或短横线。"
        )
    return code


def canonical_stable_code(value: Any) -> str:
    """Return Zhizhi's case-insensitive canonical code representation."""

    return str(value).strip().upper()


def build_storage_key(namespace: str, *parts: Any) -> str:
    """Build a stable filesystem key for a tenant or organization unit."""

    if namespace not in {"tenant", "organization-unit"}:
        raise ValueError(f"Unsupported storage key namespace: {namespace}")
    if not parts:
        raise ValueError("Storage key requires at least one business code part.")
    return canonical_stable_code(validate_stable_code(str(parts[-1]), "存储编码"))
