"""Worker runtime integration over SQLite and local media."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import select

from gewu_agent_runtime.adapters.mysql.models import ConversationCompactionRow
from gewu_agent_runtime.domain import Conversation, ConversationCompaction, StoredAttachment
from gewu_agent_runtime.identity import PrincipalRef, PrincipalType
from gewu_core import StorageEncryptionSettings
from gewu_core.logging import shutdown_logging
from gewu_core.redis import RedisConnectionSettings, RedisMode
from gewu_core.time import utc_now
from zhizhi_platform import (
    ChatMediaSettings,
    ZhizhiDatabaseSettings,
    ZhizhiRedisSettings,
)
from zhizhi_platform.workspace import ZhizhiWorkspaceSettings
from zhizhi_worker import runtime as runtime_module
from zhizhi_worker.settings import ZhizhiWorkerBootstrapSettings, ZhizhiWorkerSettings


async def test_worker_runtime_cleans_expired_attachment_and_closes_resources(
    tmp_path: Path,
) -> None:
    bootstrap = ZhizhiWorkerBootstrapSettings(
        PROJECT_NAME="zhizhi",
        PROJECT_HOME=tmp_path,
        INSTANCE_NAMESPACE="test",
        ENFORCE_STRONG_SECRETS=False,
    )
    settings = ZhizhiWorkerSettings(
        db=ZhizhiDatabaseSettings(enabled=True, use_sqlite=True),
        redis=ZhizhiRedisSettings(
            enabled=True,
            connection=RedisConnectionSettings(
                mode=RedisMode.STANDALONE,
                host="redis.internal",
            ),
        ),
        storage_encryption=StorageEncryptionSettings(key="worker-runtime-encryption-key"),
        media=ChatMediaSettings(root="media", pending_attachment_ttl_hours=24),
        workspace=ZhizhiWorkspaceSettings(storage_root=str(tmp_path / "vfs")),
    )
    runtime = await runtime_module._build_worker_runtime(bootstrap, settings)
    assert runtime.scene_git_sync_service is not None
    store = runtime.runtime_store
    principal = PrincipalRef(
        subscriber_id="zhizhi",
        principal_id="user-1",
        principal_type=PrincipalType.USER,
    )
    conversation = await store.create_conversation(Conversation(owner=principal))
    attachment = await store.create_attachment(
        StoredAttachment(
            attachment_id="attachment-1",
            owner=principal,
            conversation_id=conversation.conversation_id,
            request_id="request-1",
            storage_backend="local",
            resource_key="chat/expired.png",
            mime_type="image/png",
            size_bytes=5,
            created_at=utc_now() - timedelta(hours=25),
        )
    )
    await runtime.media_store.save(attachment.resource_key, b"image", attachment.mime_type)
    secret_summary = "sensitive Data Source summary"
    compaction = ConversationCompaction(
        conversation_id=conversation.conversation_id,
        generation=1,
        through_sequence=1,
        summary=secret_summary,
    )
    await store.save_compaction(compaction, expected_previous_id="")

    try:
        result = await runtime.attachment_cleanup.cleanup()

        assert result.model_dump() == {"scanned": 1, "deleted": 1, "failed": 0}
        assert await store.get_active_attachment(attachment.attachment_id, principal) is None
        assert await store.get_latest_compaction(conversation.conversation_id) == compaction
        async with runtime.sessions() as session:
            raw_summary = await session.scalar(
                select(ConversationCompactionRow.summary).where(
                    ConversationCompactionRow.id == compaction.compaction_id
                )
            )
        assert raw_summary is not None
        assert raw_summary == secret_summary
        with pytest.raises(FileNotFoundError):
            await runtime.media_store.read(attachment.resource_key)
    finally:
        await runtime_module._close_worker_runtime(runtime)
        shutdown_logging()


async def test_worker_recovers_scene_git_jobs_older_than_hard_limit_and_grace() -> None:
    captured: dict[str, object] = {}

    class _Repository:
        async def fail_stale_running_jobs(self, **kwargs: object) -> int:
            captured.update(kwargs)
            return 2

    before = utc_now()
    recovered = await runtime_module._recover_stale_scene_git_jobs(
        cast(Any, _Repository()),
        time_limit_seconds=120,
    )
    after = utc_now()

    assert recovered == 2
    assert captured["job_type"] == "scene_git_sync"
    stale_before = cast(datetime, captured["stale_before"])
    assert stale_before >= before - timedelta(seconds=180)
    assert stale_before <= after - timedelta(seconds=180)
    assert captured["message"]
    assert captured["error"]


async def test_worker_runtime_shutdown_closes_all_loop_bound_resources() -> None:
    closed: list[str] = []

    class _AsyncResource:
        def __init__(self, name: str) -> None:
            self.name = name

        async def close(self) -> None:
            closed.append(self.name)

        async def dispose(self) -> None:
            closed.append(self.name)

    runtime = SimpleNamespace(
        media_store=_AsyncResource("media"),
        db_engine=_AsyncResource("db"),
    )

    await runtime_module._close_worker_runtime(cast(Any, runtime))

    assert closed == ["media", "db"]
