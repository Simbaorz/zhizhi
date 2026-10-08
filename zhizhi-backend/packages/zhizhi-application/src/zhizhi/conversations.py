"""Stable external-to-Runtime conversation identity."""

from __future__ import annotations

import hashlib
import json

from zhizhi_platform.iam.codes import canonical_stable_code


def runtime_conversation_id(
    subscriber_id: str, group_id: str, user_id: str, *, tenant_code: str
) -> str:
    """Return a tenant-isolated Runtime ID for one principal and external conversation."""

    parts = (
        subscriber_id.strip(),
        canonical_stable_code(tenant_code),
        group_id.strip(),
        user_id.strip(),
    )
    if not all(parts):
        raise ValueError("subscriber_id, tenant_code, group_id and user_id are required")
    identity = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return f"zz_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:61]}"
