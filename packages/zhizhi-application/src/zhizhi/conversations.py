"""Stable external-to-Runtime conversation identity."""

from __future__ import annotations

import hashlib


def runtime_conversation_id(subscriber_id: str, group_id: str, user_id: str) -> str:
    """Return the stable Runtime ID for one principal and external conversation."""

    identity = ":".join((subscriber_id.strip(), group_id.strip(), user_id.strip()))
    if not all((subscriber_id.strip(), group_id.strip(), user_id.strip())):
        raise ValueError("subscriber_id, group_id and user_id are required")
    return f"zz_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:61]}"
