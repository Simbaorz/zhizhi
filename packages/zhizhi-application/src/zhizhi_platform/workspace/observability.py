"""致知 OpenTelemetry instruments for Workspace filesystem scans."""

from __future__ import annotations

from opentelemetry import metrics

from gewu_core.observability import (
    FilesystemScanRecorder,
    configure_filesystem_scan_recorder,
)

_METER = metrics.get_meter("zhizhi.server")
_FILESYSTEM_SCAN_ENTRIES = _METER.create_histogram(
    "zhizhi.filesystem.scan_entries",
    unit="{entry}",
    description="Filesystem entries examined by one bounded scan.",
)
_FILESYSTEM_SCAN_BYTES = _METER.create_histogram(
    "zhizhi.filesystem.scan_bytes",
    unit="By",
    description="File content bytes read by one bounded filesystem scan.",
)
_ZHIZHI_OPERATION_NAMES = {
    "workspace_recursive_list": "vfs_recursive_list",
    "workspace_line_visit": "vfs_content_visit",
}


def record_zhizhi_filesystem_scan(
    operation: str,
    scanned_entries: int,
    scanned_bytes: int,
    outcome: str,
) -> None:
    """Record 致知's exact low-cardinality filesystem metric contract."""

    attributes = {
        "operation": _ZHIZHI_OPERATION_NAMES.get(operation, operation),
        "outcome": outcome,
    }
    _FILESYSTEM_SCAN_ENTRIES.record(scanned_entries, attributes)
    _FILESYSTEM_SCAN_BYTES.record(scanned_bytes, attributes)


def install_zhizhi_filesystem_metrics() -> FilesystemScanRecorder:
    """Install 致知's recorder and return the previous process recorder."""

    return configure_filesystem_scan_recorder(record_zhizhi_filesystem_scan)
