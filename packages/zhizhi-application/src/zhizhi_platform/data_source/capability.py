"""Zhizhi gateway capability bound to one authorized Data Source source."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gewu_core.blocking import run_cpu_task
from zhizhi_platform.data_source.ports import DataSourceCredentialCipher
from zhizhi_platform.data_source.resolution import (
    ACTIVE_STATUS,
    ZhizhiDataSourceBindingRecord,
    ZhizhiDataSourceSourceRecord,
)
from zhizhi_platform.data_source.tool import (
    DataSourceQueryColumnMeta,
    DataSourceQueryExecution,
    DataSourceQueryOutput,
    DataSourceQueryRequest,
)
from zhizhi_platform.runtime_contracts import ZhizhiDataSourceBinding

CONFIGURED_CREDENTIAL_STATUS = "configured"
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|credential|cert|id_card|mobile|phone)",
    re.IGNORECASE,
)

Clock = Callable[[], int]


class DataSourceGateway(Protocol):
    """Transport used by a bound Zhizhi Data Source capability."""

    async def call(
        self,
        api_url: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> Any:
        """Return one decoded gateway response."""


class ZhizhiDataSourceSourceRepository(Protocol):
    """Load one Zhizhi-managed source referenced by an authorized binding."""

    async def get_source(self, source_id: str) -> ZhizhiDataSourceSourceRecord | None:
        """Return one source by ID."""


class ZhizhiDataSourceRuntimeConfig(BaseModel):
    """Decrypted source settings bound to one authorized capability."""

    model_config = ConfigDict(frozen=True)

    api_url: str = ""
    app_id: str = ""
    app_key: str = Field(default="", exclude=True, repr=False)
    app_secret: str = Field(default="", exclude=True, repr=False)
    database_key: str = ""
    exec_sources_code: str = ""
    timeout_seconds: int = 30
    row_limit: int = 50
    allow_databases: str = ""


class ZhizhiDataSourceCapabilityBuilder:
    """Create a least-privilege gateway capability for one source binding."""

    def __init__(
        self,
        repository: ZhizhiDataSourceSourceRepository,
        gateway: DataSourceGateway,
        cipher: DataSourceCredentialCipher,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._cipher = cipher
        self._clock = clock

    async def create(
        self,
        binding: ZhizhiDataSourceBindingRecord,
    ) -> ZhizhiDataSourceBinding | None:
        source = await self._repository.get_source(binding.data_source_id)
        if source is None or source.status != ACTIVE_STATUS:
            return None
        if source.credential_status != CONFIGURED_CREDENTIAL_STATUS:
            return None
        credentials = self._cipher.decrypt(source.credentials_ciphertext)
        row_limit = min(max(1, source.default_max_rows), max(1, source.hard_max_rows))
        config = ZhizhiDataSourceRuntimeConfig(
            api_url=source.api_url,
            app_id=source.app_id,
            app_key=str(credentials.get("app_key") or ""),
            app_secret=str(credentials.get("app_secret") or ""),
            database_key=source.default_database_key,
            exec_sources_code=source.exec_sources_code,
            timeout_seconds=source.timeout_seconds,
            row_limit=row_limit,
            allow_databases=source.allow_databases,
        )
        return ZhizhiDataSourceBinding(
            capability=ZhizhiHttpDataSourceCapability(
                config,
                self._gateway,
                clock=self._clock,
            ),
            database_key=config.database_key,
            row_limit=config.row_limit,
        )


class ZhizhiHttpDataSourceCapability:
    """Execute the exact Zhizhi gateway protocol for one bound source."""

    def __init__(
        self,
        config: ZhizhiDataSourceRuntimeConfig,
        gateway: DataSourceGateway,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._clock = clock

    async def query(self, request: DataSourceQueryRequest) -> DataSourceQueryOutput:
        """Build, send, and normalize one Zhizhi Data Source request."""

        started = time.monotonic()
        error = _configuration_error(self._config)
        if error:
            return _error_output(error, request, self._config.database_key, started)
        payload = _build_gateway_payload(self._config, request.raw_sql, clock=self._clock)
        response = await self._gateway.call(
            self._config.api_url,
            payload,
            float(self._config.timeout_seconds),
        )
        return await run_cpu_task(
            normalize_gateway_response,
            response,
            database_key=self._config.database_key,
            purpose=request.purpose,
            request_id=request.request_id,
            row_limit=request.row_limit,
            started=started,
        )


def _configuration_error(config: ZhizhiDataSourceRuntimeConfig) -> str:
    if not config.database_key:
        return "Data source query database_key is required."
    if not all(
        (
            config.api_url,
            config.app_id,
            config.app_key,
            config.app_secret,
            config.exec_sources_code,
        )
    ):
        return "Data source query configuration is incomplete."
    allowed = {value.strip() for value in config.allow_databases.split(",") if value.strip()}
    if allowed and config.database_key not in allowed:
        return f"Database key is not allowed: {config.database_key}"
    return ""


def _build_gateway_payload(
    config: ZhizhiDataSourceRuntimeConfig,
    sql: str,
    *,
    clock: Clock | None,
) -> dict[str, Any]:
    timestamp = str(clock() if clock is not None else int(time.time() * 1000))
    raw_signature = f"APP_ID{config.app_id}TIMESTAMP{timestamp}{config.app_key}{config.app_secret}"
    signature = hashlib.md5(raw_signature.encode("utf-8")).hexdigest()  # noqa: S324
    return {
        "appId": config.app_id,
        "appKey": config.app_key,
        "appSecret": config.app_secret,
        "timestamp": timestamp,
        "signature": signature,
        "data": {
            "databaseKey": config.database_key,
            "rawSql": sql,
            "param": {},
            "execSourcesCode": config.exec_sources_code,
        },
    }


def normalize_gateway_response(
    response: Any,
    *,
    database_key: str,
    purpose: str,
    request_id: str,
    row_limit: int,
    started: float,
) -> DataSourceQueryOutput:
    """Normalize the Zhizhi gateway's nested execution envelope."""

    response_map = response if isinstance(response, Mapping) else {}
    response_data = response_map.get("data", response)
    gateway_request_id = _extract_request_id(response_map, response_data) or request_id
    execution = _extract_execution(response_data)
    if not execution.batch_id and isinstance(response_data, Mapping):
        execution.batch_id = _string(response_data.get("batchId") or response_data.get("batch_id"))
    if not execution.exec_type and isinstance(response_data, Mapping):
        execution.exec_type = _string(
            response_data.get("execType") or response_data.get("exec_type")
        )
    gateway_error = _extract_gateway_error(response_map, response_data)
    if gateway_error:
        execution.success = False
        if not execution.message:
            execution.message = gateway_error
        return _output(
            success=False,
            database_key=database_key,
            purpose=purpose,
            request_id=gateway_request_id,
            execution=execution,
            error=gateway_error,
            started=started,
        )

    raw_rows = _extract_rows(response_data)
    execution_error = _execution_error(execution)
    rows = [] if execution_error else _extract_business_rows(raw_rows)
    columns = [] if execution_error else _extract_columns(raw_rows)
    column_meta = [] if execution_error else _extract_column_meta(raw_rows)
    truncated = len(rows) > row_limit
    rows = [_redact_row(row) for row in rows[:row_limit]]
    return _output(
        success=not execution_error,
        database_key=database_key,
        purpose=purpose,
        request_id=gateway_request_id,
        execution=execution,
        columns=columns,
        column_meta=column_meta,
        rows=rows,
        truncated=truncated,
        error=execution_error,
        started=started,
    )


def _extract_request_id(response: Mapping[str, Any], response_data: Any) -> str:
    for value in (response, response_data if isinstance(response_data, Mapping) else {}):
        for key in ("requestId", "request_id", "traceId", "trace_id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _extract_gateway_error(response: Mapping[str, Any], response_data: Any) -> str:
    candidates: list[Mapping[str, Any]] = [response] if response else []
    if isinstance(response_data, Mapping):
        candidates.append(response_data)
        nested = response_data.get("data")
        if isinstance(nested, Mapping):
            candidates.append(nested)
    for candidate in candidates:
        if candidate.get("success") is False:
            return _format_business_error(candidate, "")
        code = _first_text(
            candidate,
            ("code", "statusCode", "errorCode", "retCode", "resultCode"),
        )
        if code and not _success_code(code):
            return _format_business_error(candidate, code)
    return ""


def _success_code(code: str) -> bool:
    lowered = code.lower()
    if lowered in {"success", "ok", "true"}:
        return True
    if code.isdigit():
        value = int(code)
        return value == 0 or 200 <= value < 300
    return False


def _format_business_error(response: Mapping[str, Any], code: str) -> str:
    message = _first_text(
        response,
        ("error", "message", "msg", "errorMessage", "errorMsg", "reason"),
    )
    if code and message:
        return f"Data source query gateway returned code {code}: {message}"
    if code:
        return f"Data source query gateway returned code {code}."
    return message or "Data source query gateway returned failure."


def _extract_execution(response_data: Any) -> DataSourceQueryExecution:
    response_map = response_data if isinstance(response_data, Mapping) else {}
    rows = _extract_rows(response_data)
    row = next((value for value in rows if _is_execution_wrapper(value)), {})
    if not row:
        return DataSourceQueryExecution(
            success=False,
            message="Data source query gateway response is missing execution result.",
        )
    status = _first_text(row, ("status",)) or _first_text(response_map, ("status",))
    message = _first_text(
        row,
        ("msg", "message", "error", "errorMessage", "errorMsg", "reason"),
    ) or _first_text(
        response_map,
        ("message", "msg", "errorMessage", "errorMsg", "reason"),
    )
    return DataSourceQueryExecution(
        success=not status or status == "1",
        status=status,
        message=message,
        tab_name=_first_text(row, ("tabName", "tableName", "table", "name")),
        sql_info=_first_text(row, ("sqlInfo", "sql_info", "sql"))
        or _first_text(response_map, ("sqlStr", "rawSql", "sqlInfo", "sql_info")),
        consume_time_ms=_integer(row.get("consumeTime")),
        batch_item_id=_first_text(row, ("bachItemId", "batchItemId", "batch_item_id")),
        batch_id=_first_text(response_map, ("batchId", "batch_id")),
        exec_type=_first_text(response_map, ("execType", "exec_type")),
    )


def _execution_error(execution: DataSourceQueryExecution) -> str:
    if execution.success:
        return ""
    prefix = (
        f"Data source query returned status {execution.status}"
        if execution.status
        else "Data source query failed"
    )
    if execution.tab_name:
        prefix = f"{prefix} for {execution.tab_name}"
    return f"{prefix}: {execution.message}" if execution.message else f"{prefix}."


def _extract_rows(response_data: Any) -> list[dict[str, Any]]:
    if not isinstance(response_data, Mapping):
        return []
    value = response_data.get("data")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [_row(item) for item in value]


def _extract_business_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        nested = row.get("data")
        if (
            _is_execution_wrapper(row)
            and isinstance(nested, Sequence)
            and not isinstance(nested, str | bytes | bytearray)
        ):
            values.extend(_row(item) for item in nested)
    return values


def _extract_columns(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    for row in rows:
        fields = row.get("fields")
        if not isinstance(fields, Mapping):
            continue
        columns = fields.get("columns")
        if isinstance(columns, Sequence) and not isinstance(columns, str | bytes | bytearray):
            return [str(column) for column in columns if str(column).strip()]
    return []


def _extract_column_meta(
    rows: Sequence[Mapping[str, Any]],
) -> list[DataSourceQueryColumnMeta]:
    for row in rows:
        raw_meta = row.get("meta")
        if not isinstance(raw_meta, Sequence) or isinstance(raw_meta, str | bytes | bytearray):
            continue
        return [
            DataSourceQueryColumnMeta(
                field=_string(item.get("field")),
                name=_string(item.get("name")),
                description=_string(item.get("description")),
                name_in_dictionary=_string(item.get("nameInDictionary")),
                description_in_dictionary=_string(item.get("descriptionInDictionary")),
                risk_level=_integer(item.get("riskLevel")),
            )
            for item in raw_meta
            if isinstance(item, Mapping)
        ]
    return []


def _is_execution_wrapper(row: Mapping[str, Any]) -> bool:
    return "status" in row and any(
        key in row
        for key in (
            "msg",
            "tabName",
            "tableName",
            "sqlInfo",
            "consumeTime",
            "bachItemId",
            "batchItemId",
            "fields",
            "meta",
        )
    )


def _redact_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): "***" if _SENSITIVE_KEY_PATTERN.search(str(key)) else value
        for key, value in row.items()
    }


def _error_output(
    error: str,
    request: DataSourceQueryRequest,
    database_key: str,
    started: float,
) -> DataSourceQueryOutput:
    return _output(
        success=False,
        database_key=database_key,
        purpose=request.purpose,
        request_id=request.request_id,
        execution=DataSourceQueryExecution(success=False, message=error),
        error=error,
        started=started,
    )


def _output(
    *,
    success: bool,
    database_key: str,
    purpose: str,
    request_id: str,
    execution: DataSourceQueryExecution,
    columns: list[str] | None = None,
    column_meta: list[DataSourceQueryColumnMeta] | None = None,
    rows: list[dict[str, Any]] | None = None,
    truncated: bool = False,
    error: str = "",
    started: float,
) -> DataSourceQueryOutput:
    values = rows or []
    return DataSourceQueryOutput(
        success=success,
        database_key=database_key,
        purpose=purpose,
        execution=execution,
        columns=columns or [],
        column_meta=column_meta or [],
        rows=values,
        row_count=len(values),
        truncated=truncated,
        duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        request_id=request_id,
        error=error,
    )


def _first_text(value: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        candidate = value.get(key)
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return ""


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {"value": value}


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _integer(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0
