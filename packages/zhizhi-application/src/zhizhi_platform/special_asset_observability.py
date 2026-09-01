"""Zhizhi Skill and Scene directory-query timing logs."""

from __future__ import annotations

import logging
import time

_SLOW_ENTRY_LIST_MILLISECONDS = 500.0

logger = logging.getLogger(__name__)


def log_special_asset_entries_timing(
    *,
    asset_dir: str,
    path: str,
    source: str,
    actor_scope_milliseconds: float,
    path_resolve_milliseconds: float,
    source_milliseconds: float,
    started_at: float,
    entries: int,
) -> None:
    """Record Zhizhi's segmented special-asset directory query timing."""

    total_milliseconds = (time.perf_counter() - started_at) * 1000
    log_timing = (
        logger.warning if total_milliseconds >= _SLOW_ENTRY_LIST_MILLISECONDS else logger.info
    )
    log_timing(
        "Special asset entries timing asset_dir=%s path=%s source=%s "
        "actor_scope_ms=%.1f path_resolve_ms=%.1f source_ms=%.1f total_ms=%.1f entries=%d",
        asset_dir,
        path,
        source,
        actor_scope_milliseconds,
        path_resolve_milliseconds,
        source_milliseconds,
        total_milliseconds,
        entries,
    )
