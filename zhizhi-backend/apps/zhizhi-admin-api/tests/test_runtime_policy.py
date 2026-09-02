"""致知 Admin process dependency constraints."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zhizhi_admin_api.settings import AdminApiSettings


def test_admin_process_always_requires_redis() -> None:
    with pytest.raises(ValidationError, match="redis.enabled"):
        AdminApiSettings(redis={"enabled": False})

    assert AdminApiSettings().redis.enabled is True
