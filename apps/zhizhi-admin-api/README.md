# 致知 Admin API

Dedicated management process for 致知. It owns administrator authentication and RBAC, tenants,
arbitrary-depth organization trees, models, data sources, Git repositories, Scenes, Skills,
resource entitlements, bindings, and audit-backed mutations. The process does not start the Agent
Runtime.

Management scopes are either `tenant` or `organization_unit`. An organization unit is selected by
ID and resolved through its complete parent path; no organization depth is encoded in the API.

In `dev` and `test` modes, startup creates missing application and Agent Runtime tables through
SQLAlchemy metadata. Production startup never issues schema DDL. This service, the Web API, and
the Worker must use the same database, Redis deployment, Workspace storage root, and encryption
key.

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy
uv run zhizhi-admin-api
```
