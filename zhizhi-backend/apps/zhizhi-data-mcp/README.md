# Zhizhi Data MCP

This independently deployed app exposes only `query_business_data` through the official MCP
Python SDK over Streamable HTTP. It connects to Admin-configured MySQL and PostgreSQL sources;
it does not use a business SQL gateway and is not a Gewu built-in tool.

The platform database stores encrypted source configuration, organization entitlements, and
multi-source binding sets. The MCP service reads that database with its own platform
connection pool. Business connection pools are separate and created only on first use.

## Start

Initialize the platform schema with Admin first, then copy `conf/data-mcp.example.yml` to the
deployment's `conf/data-mcp.yml`. Use the same platform database and `STORAGE_ENCRYPTION_KEY`
as Admin. Set `DATA_MCP_ENABLED=true` and a shared, random `DATA_MCP_SIGNING_KEY` of at least
32 bytes in the Web API, Admin API, and MCP service processes. The source's MCP endpoint and
server ID must match `data_mcp.public_url` and `data_mcp.server_id` for the chosen service.

From `zhizhi-backend/`, with `PROJECT_HOME` pointing to the repository root:

```sh
uv sync --all-packages --all-extras --all-groups --frozen
CONFIG_FILE=conf/data-mcp.yml uv run zhizhi-data-mcp --host 127.0.0.1 --port 8002
```

`scripts/start-local.sh` starts this service together with the APIs and Worker; no extra startup
flag is needed. Prepare `conf/data-mcp.yml` with `data_mcp.enabled: true` and configure the
Web/Admin query clients before running the launcher. `DATA_MCP_ENABLED` remains an optional
environment override for the processes' `data_mcp.enabled` configuration, not a launcher switch.
Real credentials are deployment configuration; the checked-in example deliberately contains no
usable keys.

## Configuration ownership

The three configuration files belong to independently running processes:

| Process | Role of `data_mcp` |
| --- | --- |
| Web API (`conf/web.yml`) | Enable the query client and sign grants for Agent queries. |
| Admin API (`conf/admin.yml`) | Enable the probe client and sign grants for source connection tests. |
| Data MCP (`conf/data-mcp.yml`) | Enable the server, verify grants, and manage database connection pools. |

Web and Admin use the same client configuration fields: `enabled`, `signing_key`,
`token_ttl_seconds`, and `max_client_connections` (the per-process HTTP connection limit,
default 64). The server uses `enabled`, `signing_key`, `server_id`, `public_url`,
`max_pool_capacity`, `max_active_pools`, `idle_pool_seconds`, and `shutdown_timeout_seconds`.
Client and server configuration models reject YAML fields that belong only to the other role.

`server_id` is the identity of one running Data MCP server. In Admin's source form, set
**Service number** (`server_id`) and **MCP address** (`endpoint_url`) to that server's identity
and `public_url`. Those values are saved per source in the platform database. Web and Admin
route requests and sign their target claims from that source record; their YAML files do not
select a single global server. Different sources may target different MCP servers, each with
its own server ID, public URL, and pool budget. `public_url` is the advertised resource URL;
the command's `--host` and `--port` options control the listening address. Its path sets the
HTTP endpoint path. Transport Host/Origin checks allow the configured public authority;
reverse proxies must preserve that Host header.

All three processes use the same `ZhizhiDatabaseSettings` schema. Each example lists the full
`db` section, including SQLite selection, the remote `url`, and platform connection-pool and
timeout settings. They must target the same platform database. With SQLite, use the same
`PROJECT_HOME` and `sqlite_file_name` to resolve the same file; independently deployed services
should share a reachable platform database. With `use_sqlite=false`, configure `db.url` (or
`DB_URL`). Pool sizes and timeouts may differ per process. `db.pool_size` / `db.max_overflow`
govern platform metadata access, while `data_mcp.max_pool_capacity` and each Admin-managed
source's `pool_size` govern business database access.

All three processes must use the same `signing_key`. Supply it through the shared
`DATA_MCP_SIGNING_KEY` environment variable instead of copying secrets into YAML files.
The local launcher passes its environment to all three processes. Each deployment process
still needs that environment variable when started separately.

Web and Admin use `data_mcp.token_ttl_seconds` (or `DATA_MCP_TOKEN_TTL_SECONDS`) to set grant
lifetimes. It defaults to 60 seconds and must be positive. Each query or probe receives a newly
signed token. The server validates the token's signed `exp` claim, so it does not need a matching
lifetime setting. Expiration prevents admission of an expired request; an accepted query is
bounded by its database timeout. An expired request fails without automatic retry; a subsequent
call receives a fresh token.

## Resource flow

1. A platform administrator adds a physical source and encrypted database password in Global
   Management → Data Sources. Supply a database account with read-only privileges.
2. The administrator allocates it to a tenant, then strict-parent administrators delegate it
   down the arbitrary-depth organization tree.
3. The scope binds one or more sources from its available pool and chooses one default.
4. The nearest active binding set is inherited as a whole. Every selected source must remain
   entitled along the complete current organization path. Sets are never merged across scopes.
5. The Agent reads a Wiki table dictionary's `data_source_tag` and invokes the model-facing Tool
   with `sql`, optional named `parameters`, `purpose`, and optional `data_source_tag`. The tool
   schema lists only current tags. Omitting the tag uses the default; an invalid tag never
   falls back to another source.
6. Zhizhi rereads authorization and maps the tag to an endpoint and physical source ID. The
   official MCP client sends a short-lived, source-bound signed grant outside model arguments.
7. The MCP server checks that grant and rereads tenant status, current organization path,
   binding, entitlements, source status and connection revision before querying.

No available binding or a disabled MCP integration means no query tool is exposed. Connection
probes are super-admin only, use a distinct signed grant, and always execute a fixed `SELECT 1`
regardless of supplied query arguments. Source passwords never travel over MCP or reach the model.

## Query and pool limits

SQL uses the selected database's dialect and `:name` placeholders, with parameters supplied as
JSON values. Only a single SELECT/WITH query is accepted. Parsed DML/DDL, locking SELECTs,
SELECT INTO, cross-allowlist schema references and known side-effect functions are rejected.
Database read-only transactions and the read-only account provide the execution boundary.

Source entitlements authorize that account's database/schema access. They do not synthesize
business row-level filters. Use tenant-specific read-only sources/accounts or database-enforced
row policies when different tenants must see different rows within one physical database.

Queries without a LIMIT receive a bounded LIMIT; a larger explicit LIMIT is rejected.
Results stream through row and byte limits, with columns, rows, row count, truncation and the
logical tag returned as structured MCP data. Timeouts/cancellation invalidate uncertain driver
connections. A query never spans multiple physical sources; the Agent may make separate calls.

Each pool is keyed by source ID and connection revision. Pools use bounded capacity and no
overflow. Process-wide capacity includes idle and draining pools, not just active queries.
Old generations finish their leased queries and then close. Capacity pressure evicts only idle
pools or waits for a bounded interval. An idle maintenance task also observes disabled/deleted
sources, changed revisions and server reassignment, then disposes their idle pools.

Connection-related edits increment the connection revision; ordinary resource edits do not.
Resource updates use optimistic revisions, and stale connection-test results cannot overwrite
new configurations. Multiply each process's pool budget by its worker/replica count when planning
database capacity. Shutdown stops new leases, cancels query tasks and closes pools.

The PyMySQL dependency is constrained to 1.1.2 because the pinned SQLAlchemy 2.0.49 release has
an upstream async pool-pre-ping incompatibility with PyMySQL 1.2. This preserves health checks.

## Verification

The SDK protocol test uses an in-process ASGI transport with a temporary platform database and
an isolated SQLite query engine. Real MySQL/PostgreSQL connector checks are available against
disposable localhost containers using `ZHIZHI_TEST_MYSQL_PORT` and
`ZHIZHI_TEST_POSTGRESQL_PORT`; they never read deployment credentials.
