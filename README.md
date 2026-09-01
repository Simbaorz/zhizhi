# Zhizhi Backend

[简体中文](README.zh-CN.md)

Zhizhi Backend is the enterprise application layer built on the [Gewu Agent Runtime](https://github.com/Simbaorz/gewu). It turns Gewu's business-neutral execution, context, memory, conversation, Tool, Scene, Skill, and virtual-filesystem capabilities into a deployable knowledge-question-answering service with tenant isolation, organization-aware resource governance, management APIs, and a minimal integration API.

It is designed to sit behind an enterprise system. The host system keeps ownership of end-user authentication, product UI, and business authorization; Zhizhi accepts a trusted tenant, active organization unit, and principal context, resolves the effective Agent capabilities, and runs the turn.

## What is included

- `apps/zhizhi-web-api`: streaming Agent API for enterprise integration.
- `apps/zhizhi-admin-api`: administrator authentication, RBAC, organization, model, data-source, Git, Scene, and Skill management.
- `apps/zhizhi-worker`: Scene Git synchronization and scheduled background jobs.
- `packages/zhizhi-application`: transport-neutral application services, persistence adapters, resource resolution, audit, and workspace composition.

## Organization and resource model

Tenant is the isolation boundary. Every tenant owns an arbitrary-depth organization tree:

```text
tenant
└── organization unit
    └── organization unit
        └── ...
```

Organization units use `parent_id`; names such as division, branch, region, department, team, and project are data, not schema levels. A request selects one active organization unit and Zhizhi validates its complete root-to-leaf path.

Models and data sources distinguish two concepts:

- Entitlement: the resource is available to a tenant or organization unit and may be delegated further.
- Binding: the resource is selected for execution at that scope.

At runtime, bindings resolve from the active leaf toward its ancestors and finally the tenant. The nearest valid binding wins. A binding never bypasses entitlement checks. Tenant Scene and Skill assets are mounted into the read-only Agent workspace together with the active organization path.

## Web API surface

The Web API intentionally stays small so an enterprise can embed it without adopting another user system or complete chat product:

- `POST /api/agent/chat/stream`
- `POST /api/agent/chat/ask-answer`
- `POST /api/agent/chat/attachments`
- `GET /api/agent/chat/attachments/{attachment_id}`
- `GET /api/agent/capabilities`
- `GET /api/agent/skills`
- `GET /api/agent/scenes`
- `GET /api/agent/conversations/{conversation_id}/messages`
- `GET /api/agent/conversations/{conversation_id}/pending-ask`
- `POST /api/agent/conversations/{conversation_id}/interrupt`

The trusted caller context is:

```json
{
  "conversation_id": "conversation-123",
  "tenant_id": "tenant-123",
  "active_organization_unit_id": "team-456",
  "principal_id": "user-789",
  "principal_type": "user"
}
```

Zhizhi does not expose end-user login, profiles, or a conversation-list product. The host application must authenticate the caller and construct this context.

## Local development

Requirements: Python 3.12+, `uv`, and a sibling Gewu checkout.

```bash
uv sync --all-packages --all-extras --all-groups --frozen
cp conf/web.example.yml conf/web.yml
cp conf/admin.example.yml conf/admin.yml
cp conf/worker.example.yml conf/worker.yml
./scripts/start-local.sh
```

The script starts the Web API on `127.0.0.1:8000`, the Admin API on `127.0.0.1:8001`, and a Celery worker with its scheduler. Local configuration files and credentials must remain outside Git.

In `dev` and `test` modes, missing tables are created from SQLAlchemy metadata. Production mode never executes schema DDL; provision the schema before starting the services. All processes must share the same database, Redis deployment, workspace storage root, and storage-encryption key.

## Verification

```bash
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
uv build --all-packages
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
