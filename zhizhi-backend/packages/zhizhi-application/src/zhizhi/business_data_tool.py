"""Model-visible tag selection backed exclusively by the authorized MCP client."""

from __future__ import annotations

from typing import Any

from gewu_agent_runtime.tools import PersistencePolicy, Tool, ToolContext, ToolResult
from zhizhi_platform.data_source.domain import SourceSelection
from zhizhi_platform.data_source.mcp_client import DataMcpClient
from zhizhi_platform.data_source.resolution import DataSourceResolver
from zhizhi_platform.iam import AccessScope


def build_business_data_tool(
    selection: SourceSelection,
    resolver: DataSourceResolver,
    client: DataMcpClient,
    scope: AccessScope,
) -> Tool:
    tags = [source.tag for source in selection.sources]
    dialects = ", ".join(f"{source.tag}={source.driver}" for source in selection.sources)

    async def execute(arguments: dict[str, Any], _context: ToolContext) -> ToolResult:
        try:
            current = await resolver.resolve(scope)
            if current is None:
                return ToolResult(
                    output={"error": "No data sources are currently bound."}, is_error=True
                )
            tag = str(arguments.get("data_source_tag") or current.default_tag).strip().upper()
            source = next((item for item in current.sources if item.tag == tag), None)
            if source is None:
                return ToolResult(
                    output={
                        "error": "Requested tag is unavailable; do not query another source.",
                        "available_data_source_tags": [item.tag for item in current.sources],
                    },
                    is_error=True,
                )
            result = await client.query(
                source,
                scope,
                str(arguments["sql"]),
                dict(arguments.get("parameters") or {}),
                str(arguments["purpose"]),
            )
            return ToolResult(output=result, model_payload=result)
        except Exception:
            return ToolResult(
                output={
                    "error": "Data query failed. Check the selected tag, SQL and service availability; do not substitute another data source."
                },
                is_error=True,
            )

    return Tool(
        name="query_business_data",
        category="data",
        allow_parallel=True,
        description=(
            "Query business records when needed to answer a user question or verify a business condition. "
            "Use Wiki/file tools to find documents and table dictionaries. Before querying, read the current Wiki's "
            "table dictionary to identify the tables, columns, relationships and data_source_tag; do not guess them. "
            "Each call executes one read-only SELECT/WITH query against one data source. "
            "Select only necessary columns and include relevant filters; use aggregates when totals are needed. "
            "If the selected tag is unavailable or its query fails, do not substitute another data source. "
            "Returns columns, rows, row count, the data source tag and a truncation flag."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "maxLength": 65536,
                    "description": (
                        "One complete read-only SELECT/WITH statement using the Wiki's table and column definitions. "
                        "Include necessary filters, such as record IDs, date ranges or status. "
                        "Use named :parameter placeholders for filter values and supply them in parameters. "
                        f"Use the selected source's SQL dialect: {dialects}."
                    ),
                },
                "parameters": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": (
                        "Values bound to the SQL's named placeholders, with keys excluding the colon. "
                        'For example, sql="SELECT id FROM orders WHERE id = :order_id" uses parameters={"order_id": 123}. '
                        "Keys must exactly match the placeholder names. Omit or pass {} when there are no placeholders."
                    ),
                },
                "purpose": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 512,
                    "description": (
                        "Short explanation of the business question or condition this query will verify, "
                        "such as checking whether an order has been paid."
                    ),
                },
                "data_source_tag": {
                    "type": "string",
                    "enum": tags,
                    "description": (
                        "Data source tag specified by the user or the current Wiki's table dictionary. "
                        f"Available tags: {', '.join(tags)}. Default tag: {selection.default_tag}. "
                        "Omit only when neither the user nor the Wiki specifies a tag; omission uses the default source."
                    ),
                },
            },
            "required": ["sql", "purpose"],
            "additionalProperties": False,
        },
        function=execute,
        persistence_policy=PersistencePolicy.PROTECTED,
        trace_result=False,
        retry_on_failure=False,
        max_retries=0,
    )
