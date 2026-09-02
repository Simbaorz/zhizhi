# Zhizhi Backend

[简体中文](README.zh-CN.md) · [Back to the project overview](../README.md)

Zhizhi Backend is where an authenticated enterprise question becomes a governed Agent run.

It sits between the enterprise host and the [Gewu Agent Runtime](https://github.com/Simbaorz/gewu). The host keeps control of users, business permissions, and product experience. The backend validates the supplied tenant and organization context, resolves the capabilities allowed for that scope, composes a read-only workspace and ToolSet, and then asks Gewu to execute and persist the conversation.

## What happens during one turn

```text
trusted caller context
        │
        ▼
tenant and organization-path validation
        │
        ├─ nearest model binding
        ├─ nearest data-source binding
        ├─ visible Scene and Skill catalog
        └─ tenant + organization workspace mounts
        │
        ▼
read-only Zhizhi ToolSet
        │
        ▼
Gewu Agent Runtime
        │
        ├─ stream model and tool events
        ├─ persist messages and conversation state
        ├─ suspend and resume ask_user
        ├─ compact long context
        └─ accept interrupt
```

The backend does not infer identity from a public browser request. Its Agent API is designed to sit behind a trusted enterprise gateway or application that authenticates the caller before constructing the context.

## Workspace layout

This directory is a Python `uv workspace`:

| Module | Responsibility |
| --- | --- |
| [`apps/zhizhi-web-api`](apps/zhizhi-web-api/README.md) | Small, streaming Agent API for integration with enterprise applications |
| [`apps/zhizhi-admin-api`](apps/zhizhi-admin-api/README.md) | Administrator authentication, RBAC, tenants, organizations, resources, Scenes, Skills, and audited mutations |
| [`apps/zhizhi-worker`](apps/zhizhi-worker/README.md) | Celery worker and scheduler for Scene Git synchronization and attachment cleanup |
| `packages/zhizhi-application` | Transport-neutral application services, resource policies, persistence adapters, Runtime composition, and managed workspace support |

All processes use the same application package and must agree on the database, Redis topology, workspace storage root, media storage, and storage-encryption key.

## Identity and organization model

Tenant is the hard isolation boundary. Organization units form an arbitrary-depth tree:

```text
tenant
└── organization unit
    ├── organization unit
    │   └── organization unit
    └── organization unit
```

An organization unit has a parent, an external key, a display name, a type, metadata, and status. Terms such as region, branch, department, team, and project remain data; they are not schema levels.

Principals and groups are separate from the tree. A principal may be associated with organization units and groups without forcing the enterprise's identity model into the organization schema.

The Web API receives:

```json
{
  "conversation_id": "conversation-123",
  "tenant_id": "tenant-123",
  "active_organization_unit_id": "team-456",
  "principal_id": "user-789",
  "principal_type": "user"
}
```

The active organization unit is optional for tenant-level operation. When present, the backend validates the complete root-to-leaf path before resolving any capability.

## Entitlements, bindings, and inheritance

Resource governance separates availability from selection:

| Concept | Meaning |
| --- | --- |
| Entitlement | The resource is available at a tenant or organization scope and may be delegated according to policy |
| Binding | The authorized resource is selected for execution at that scope |

Model and data-source bindings resolve from the active organization leaf toward its ancestors and finally the tenant. The first valid binding wins. If the nearest active binding exists but its capability cannot be created, the request fails instead of silently skipping to a broader scope.

Runtime knowledge is assembled differently: the tenant workspace and every organization workspace on the active path are mounted read-only. In the current release, managed Scene and Skill assets are tenant-scoped and are exposed only when visible to the resolved caller scope.

## Runtime capabilities

The first open-source release deliberately exposes a bounded ToolSet:

- `list`, `read`, `glob`, and `grep` for read-only workspace discovery;
- `skill` for loading a governed Skill;
- `ask_user` for pausing a run and requesting structured clarification;
- optional `query_data_source` when an authorized data-source binding resolves.

There is no shell tool and no unrestricted workspace mutation.

### Business data without database credentials in the model

`query_data_source` does not connect the Agent directly to a database. Zhizhi binds it to an administrator-configured HTTP data gateway. The current reference adapter:

- accepts only a single `SELECT` or `WITH` statement;
- rejects mutation and DDL keywords;
- applies a configured row limit and maximum Tool result size;
- keeps gateway credentials on the server;
- normalizes the gateway response and masks values under sensitive-looking column names.

The gateway protocol is an application adapter, not a Gewu requirement. Enterprises can replace it with an adapter for their own governed query service while keeping the Runtime contract bounded.

## Agent Web API

The integration surface stays intentionally small:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/agent/chat/stream` | Start an Agent turn and receive Server-Sent Events |
| `POST` | `/api/agent/chat/ask-answer` | Resume a pending `ask_user` interaction |
| `POST` | `/api/agent/chat/attachments` | Upload an image before a turn |
| `GET` | `/api/agent/chat/attachments/{attachment_id}` | Read an authorized attachment |
| `GET` | `/api/agent/capabilities` | Resolve capabilities for the supplied scope |
| `GET` | `/api/agent/skills` | List visible Skills |
| `GET` | `/api/agent/scenes` | List visible Scenes |
| `GET` | `/api/agent/conversations/{conversation_id}/messages` | Read persisted messages |
| `GET` | `/api/agent/conversations/{conversation_id}/pending-ask` | Recover pending clarification state |
| `POST` | `/api/agent/conversations/{conversation_id}/interrupt` | Interrupt the active run |
| `GET` | `/healthz` | Process liveness |
| `GET` | `/readyz` | Runtime readiness |

Requests use `request_id` for idempotency. Reusing one request ID for different work returns a conflict instead of starting a duplicate turn.

## Admin API

The management process is separate from Agent execution. It provides:

- administrator login, encrypted password transport, session handling, login throttling, RBAC, and permission-aware navigation;
- tenants, recursive organization units, administrator accounts, tenant memberships, and roles;
- model definitions, encrypted credentials, connectivity tests, entitlements, and bindings;
- HTTP data-source definitions, encrypted gateway credentials, entitlements, and bindings;
- Git repositories and tenant entitlements;
- managed Scene and Skill files, packages, manifests, and Scene Git synchronization;
- mutation audit records and bounded upload/download handling.

It does not start the Agent Runtime.

## Configuration model

Each process loads bootstrap values from the environment and service settings from YAML or Apollo.

Common bootstrap variables include:

- `PROJECT_NAME`, `PROJECT_HOME`, `MODE`, and `TIMEZONE`;
- `CONFIG_SOURCE`: `local` or `apollo`;
- `CONFIG_FILE` for an explicit YAML path;
- Apollo connection variables when `CONFIG_SOURCE=apollo`.

The tracked examples are:

- [`conf/web.example.yml`](conf/web.example.yml)
- [`conf/admin.example.yml`](conf/admin.example.yml)
- [`conf/worker.example.yml`](conf/worker.example.yml)

Real configuration files and credentials are ignored by Git.

The Web API, Admin API, and Worker must use compatible values for:

- database connection and schema;
- Redis application and Celery databases;
- `workspace.storage_root`;
- media filesystem or object-storage configuration;
- `storage_encryption.key`.

In production, the JWT signing key and storage-encryption key must be distinct secrets. Admin session cookies should be secure and all services should run behind TLS.

## Local development

Requirements:

- Python 3.12+
- `uv`
- Redis
- Git when using Scene Git synchronization
- OpenSSL for generating the local Admin password-transport key

Install the workspace:

```bash
uv sync --all-packages --all-extras --all-groups --frozen
```

Create ignored local configuration:

```bash
cp conf/web.example.yml conf/web.yml
cp conf/admin.example.yml conf/admin.yml
cp conf/worker.example.yml conf/worker.yml
mkdir -p .local
openssl genpkey -algorithm RSA -out .local/admin-password-key.pem -pkeyopt rsa_keygen_bits:2048
```

Before starting, edit the three YAML files:

1. point `password_transport.private_key_path` at the generated private key;
2. choose writable local paths for workspace, media, and temporary data;
3. set the same non-empty `storage_encryption.key` in all three files;
4. set an Admin `jwt.sk`;
5. verify that all processes use the same database and Redis deployment.

Start the complete local stack:

```bash
./scripts/start-local.sh
```

The script starts:

- Web API at `http://127.0.0.1:8000`;
- Admin API at `http://127.0.0.1:8001`;
- Celery Worker with Beat.

Create the one-time super administrator in another terminal:

```bash
CONFIG_FILE=conf/admin.yml uv run zhizhi-admin-api init-super-admin
```

The command prompts for credentials unless explicit CLI values are supplied.

### Run processes separately

```bash
CONFIG_FILE=conf/web.yml uv run zhizhi-web-api --host 127.0.0.1 --port 8000
CONFIG_FILE=conf/admin.yml uv run zhizhi-admin-api --host 127.0.0.1 --port 8001
CONFIG_FILE=conf/worker.yml uv run zhizhi-worker worker --beat --loglevel=INFO
```

## Schema and production behavior

In `dev` and `test` modes, startup creates missing Zhizhi and Gewu tables from SQLAlchemy metadata. This is a convenience for local work, not a migration system.

In `prod` mode, the services never issue schema DDL. Provision the complete schema before starting production processes. The project currently makes no legacy-schema compatibility promise.

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

[MIT](LICENSE)
