"""Read-only data-source Tool over an authorized host capability."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, Field
from pydantic_core import to_jsonable_python

from gewu_agent_runtime.tools import Tool, ToolContext, ToolResult, tool
from gewu_core.blocking import run_cpu_task
from gewu_core.ids import new_id

_DANGEROUS_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|CALL|EXEC|LOAD|OUTFILE)\b",
    re.IGNORECASE,
)
_LIMIT_PATTERN = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|credential|cert|id_card|mobile|phone)",
    re.IGNORECASE,
)
_RESULT_TOO_LARGE_ERROR = "Data source query result exceeds the configured byte limit."
_CAPACITY_ERROR_FIELD_BYTES = 256


class DataSourceQueryExecution(BaseModel):
    success: bool = False
    status: str = ""
    message: str = ""
    tab_name: str = ""
    sql_info: str = ""
    consume_time_ms: int = 0
    batch_item_id: str = ""
    batch_id: str = ""
    exec_type: str = ""


class DataSourceQueryColumnMeta(BaseModel):
    field: str = ""
    name: str = ""
    description: str = ""
    name_in_dictionary: str = ""
    description_in_dictionary: str = ""
    risk_level: int = 0


class DataSourceQueryOutput(BaseModel):
    success: bool = False
    database_key: str = ""
    purpose: str = ""
    execution: DataSourceQueryExecution = Field(default_factory=DataSourceQueryExecution)
    columns: list[str] = Field(default_factory=list)
    column_meta: list[DataSourceQueryColumnMeta] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    duration_ms: int = 0
    request_id: str = ""
    error: str = ""


class DataSourceQueryRequest(BaseModel):
    """Validated query passed to one already-authorized subscriber capability."""

    raw_sql: str
    purpose: str
    row_limit: int = Field(ge=1)
    request_id: str


class DataSourceCapability(Protocol):
    """Execute read-only SQL without exposing source selection or credentials."""

    async def query(self, request: DataSourceQueryRequest) -> DataSourceQueryOutput:
        """Return a normalized result for one authorized query."""


@tool(
    name="query_data_source",
    category="data",
    allow_parallel=True,
    trace_result=False,
)
async def query_data_source_template(
    raw_sql: str,  # noqa
    purpose: str,
    *,
    runtime: ToolContext,  # noqa
) -> ToolResult:
    """Query configured data sources with complete read-only SQL.

    Use this tool when data source is needed to verify a troubleshooting
    hypothesis or answer a user question. Only SELECT/WITH queries are allowed.
    Do not use this for wiki/file search.

    Usage:
    - Pass a complete executable SQL string in `raw_sql`; parameter binding is
      not supported.
    - Include necessary filters directly in `raw_sql`, such as phone number,
      user ID, product ID, date range, or status.
    - Write a narrow SELECT/WITH query and include enough filters to avoid broad
      scans. The tool enforces a row limit, but the SQL should still be
      specific.
    - Pass `purpose` as a short explanation of what the query is verifying.

    Args:
        raw_sql: Complete read-only SELECT/WITH SQL to execute.
        purpose: Short explanation of the verification goal.

    Returns:
        A data source query result with success status, summary, returned rows,
        row count, truncation flag, and error details when the query fails.
    """

    del raw_sql, runtime
    return _error_result(
        "Data source query runtime configuration is unavailable.",
        database_key="",
        purpose=purpose.strip(),
        request_id=new_id(),
        started=time.monotonic(),
        max_result_bytes=512 * 1024,
    )


def data_source_tool(
    capability: DataSourceCapability,
    *,
    database_key: str = "",
    row_limit: int = 20,
    max_result_bytes: int = 512 * 1024,
    request_id_factory: Callable[[], str] = new_id,
) -> Tool:
    """Bind the exact Tool to a subscriber-authorized data capability."""

    if row_limit < 1:
        raise ValueError("row_limit must be positive.")
    if max_result_bytes < 2048:
        raise ValueError("Data source ToolResult capacity must be at least 2048 bytes.")

    async def execute(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        del context
        started = time.monotonic()
        request_id = request_id_factory()
        purpose = str(arguments.get("purpose") or "").strip()
        sql = str(arguments.get("raw_sql") or "")
        if not purpose:
            return _error_result(
                "Data source query purpose is required.",
                database_key=database_key,
                purpose=purpose,
                request_id=request_id,
                started=started,
                max_result_bytes=max_result_bytes,
            )
        if not sql.strip():
            return _error_result(
                "Data source query SQL is required.",
                database_key=database_key,
                purpose=purpose,
                request_id=request_id,
                started=started,
                max_result_bytes=max_result_bytes,
            )
        normalized, error = normalize_and_validate_sql(sql)
        if error:
            return _error_result(
                error,
                database_key=database_key,
                purpose=purpose,
                request_id=request_id,
                started=started,
                max_result_bytes=max_result_bytes,
            )
        request = DataSourceQueryRequest(
            raw_sql=enforce_limit(normalized, row_limit),
            purpose=purpose,
            row_limit=row_limit,
            request_id=request_id,
        )
        try:
            output = await capability.query(request)
        except Exception as exc:  # noqa: BLE001
            return _error_result(
                f"Data source query failed: {exc}",
                database_key=database_key,
                purpose=purpose,
                request_id=request_id,
                started=started,
                max_result_bytes=max_result_bytes,
            )
        return await run_cpu_task(
            _normalize_and_bound_result,
            output,
            request=request,
            database_key=database_key,
            started=started,
            max_result_bytes=max_result_bytes,
        )

    return query_data_source_template.model_copy(update={"function": execute})


def normalize_and_validate_sql(sql: str) -> tuple[str, str]:
    """Normalize one statement and enforce the reference read-only SQL policy."""

    normalized = sql.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].strip()
    if ";" in normalized:
        return normalized, "Data source query does not allow multiple SQL statements."
    check_sql = _strip_leading_comments(normalized)
    if not re.match(r"^(SELECT|WITH)\b", check_sql, re.IGNORECASE):
        return normalized, "Data source query only allows SELECT or WITH SQL."
    if _DANGEROUS_SQL_PATTERN.search(check_sql):
        return normalized, "Data source query SQL contains a forbidden keyword."
    return normalized, ""


def enforce_limit(sql: str, row_limit: int) -> str:
    matches = list(_LIMIT_PATTERN.finditer(sql))
    if not matches:
        return f"{sql} limit {row_limit}"
    match = matches[-1]
    if int(match.group(1)) <= row_limit:
        return sql
    return f"{sql[: match.start(1)]}{row_limit}{sql[match.end(1) :]}"


def _strip_leading_comments(sql: str) -> str:
    remaining = sql.lstrip()
    while True:
        if remaining.startswith("--"):
            _, _, remaining = remaining.partition("\n")
            remaining = remaining.lstrip()
            continue
        if remaining.startswith("/*"):
            end = remaining.find("*/")
            if end < 0:
                return ""
            remaining = remaining[end + 2 :].lstrip()
            continue
        return remaining


def _normalize_output(
    output: DataSourceQueryOutput,
    *,
    request: DataSourceQueryRequest,
    database_key: str,
    started: float,
) -> DataSourceQueryOutput:
    rows = [{key: _redact_value(key, value) for key, value in row.items()} for row in output.rows]
    truncated = output.truncated or len(rows) > request.row_limit
    rows = rows[: request.row_limit]
    return output.model_copy(
        update={
            "database_key": output.database_key or database_key,
            "purpose": request.purpose,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "duration_ms": output.duration_ms or _duration_ms(started),
            "request_id": output.request_id or request.request_id,
        }
    )


def _normalize_and_bound_result(
    output: DataSourceQueryOutput,
    *,
    request: DataSourceQueryRequest,
    database_key: str,
    started: float,
    max_result_bytes: int,
) -> ToolResult:
    normalized = _normalize_output(
        output,
        request=request,
        database_key=database_key,
        started=started,
    )
    return _bounded_result(normalized, max_result_bytes=max_result_bytes)


def _redact_value(key: str, value: Any) -> Any:
    return "***" if _SENSITIVE_KEY_PATTERN.search(key) else value


def _error_result(
    error: str,
    *,
    database_key: str,
    purpose: str,
    request_id: str,
    started: float,
    max_result_bytes: int,
) -> ToolResult:
    return _bounded_result(
        DataSourceQueryOutput(
            success=False,
            database_key=database_key,
            purpose=purpose,
            execution=DataSourceQueryExecution(success=False, message=error),
            duration_ms=_duration_ms(started),
            request_id=request_id,
            error=error,
        ),
        max_result_bytes=max_result_bytes,
    )


def _model_payload(output: DataSourceQueryOutput) -> dict[str, Any]:
    if not output.success:
        error = output.error or output.execution.message or "Data source query failed."
        payload: dict[str, Any] = {
            "success": False,
            "summary": f"查询失败：{error}",
            "purpose": output.purpose,
            "error": error,
        }
        if output.execution.status:
            payload["status"] = output.execution.status
        return payload
    summary = f"查询成功，返回 {output.row_count} 行业务数据。"
    if output.truncated:
        summary = f"{summary} 结果已截断。"
    return {
        "success": True,
        "summary": summary,
        "purpose": output.purpose,
        "columns": output.columns,
        "rows": output.rows,
        "row_count": output.row_count,
        "truncated": output.truncated,
    }


def _tool_result(output: DataSourceQueryOutput) -> ToolResult:
    return ToolResult(
        output=output,
        model_payload=_model_payload(output),
        is_error=not output.success,
    )


def _bounded_result(
    output: DataSourceQueryOutput,
    *,
    max_result_bytes: int,
) -> ToolResult:
    result = _tool_result(output)
    if _fits(result, max_result_bytes):
        return result
    low = 0
    high = len(output.rows)
    bounded: ToolResult | None = None
    while low <= high:
        row_count = (low + high) // 2
        candidate = _tool_result(
            output.model_copy(
                update={
                    "rows": output.rows[:row_count],
                    "row_count": row_count,
                    "truncated": True,
                }
            )
        )
        if _fits(candidate, max_result_bytes):
            bounded = candidate
            low = row_count + 1
        else:
            high = row_count - 1
    if bounded is not None:
        return bounded
    error = DataSourceQueryOutput(
        success=False,
        database_key=_truncate_utf8(output.database_key, _CAPACITY_ERROR_FIELD_BYTES),
        purpose=_truncate_utf8(output.purpose, _CAPACITY_ERROR_FIELD_BYTES),
        request_id=_truncate_utf8(output.request_id, _CAPACITY_ERROR_FIELD_BYTES),
        duration_ms=output.duration_ms,
        error=_RESULT_TOO_LARGE_ERROR,
        execution=DataSourceQueryExecution(
            success=False,
            message=_RESULT_TOO_LARGE_ERROR,
        ),
    )
    result = _tool_result(error)
    if not _fits(result, max_result_bytes):
        raise RuntimeError("Data source capacity error does not fit configured byte limit.")
    return result


def _fits(result: ToolResult, max_result_bytes: int) -> bool:
    persisted = json.dumps(
        to_jsonable_python(result.raw_output_payload()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    model = json.dumps(
        to_jsonable_python(result.model_payload),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return len(persisted) <= max_result_bytes and len(model) <= max_result_bytes


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode()
    return value if len(encoded) <= max_bytes else encoded[:max_bytes].decode(errors="ignore")


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
