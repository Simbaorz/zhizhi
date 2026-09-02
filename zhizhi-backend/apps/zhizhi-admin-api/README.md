# Zhizhi Admin API

[Back to Zhizhi Backend](../../README.md)

The Admin API is the control-plane process for Zhizhi.

It answers a different question from the Agent Web API. The Web API asks, “What may this caller use for this turn?” The Admin API asks, “Who may define, delegate, bind, and change those capabilities?”

## Responsibilities

The process owns:

- administrator authentication, encrypted password transport, sessions, login throttling, and profile/password updates;
- RBAC roles, permissions, tenant memberships, and permission-aware navigation;
- tenants and arbitrary-depth organization units;
- model definitions, encrypted credentials, validation, test calls, entitlements, and bindings;
- HTTP data-source definitions, encrypted credentials, entitlements, and bindings;
- Git repositories, credential rotation, connectivity tests, and tenant entitlements;
- Scene and Skill assets, files, packages, and manifests;
- Scene Git configuration, manual synchronization requests, and job history;
- mutation auditing and bounded administration uploads/downloads.

It does not start Gewu or execute Agent turns.

## Scope model

Administrative work is performed against either a tenant or an organization unit. Organization units are selected by ID and resolved through their full parent path; the API does not encode a fixed organization depth.

Entitlements represent resources available to a scope. Bindings represent resources selected at that scope. The Admin API validates that a binding is allowed by the applicable entitlement policy.

## Configuration

The default local file is `conf/admin.yml`. Create it from `conf/admin.example.yml` at the Zhizhi repository root.

Important settings include:

- database and Redis connectivity;
- the Admin JWT signing key;
- RSA private-key path for browser password transport;
- storage-encryption key for model, data-source, and Git credentials;
- administrator login-throttle and IAM limits;
- Workspace storage and Scene Git settings;
- Celery queue settings for synchronization jobs.

Set `ADMIN_SESSION_COOKIE_SECURE=true` in production. Admin API, Web API, and Worker must use the same database, Redis deployment, Workspace root, and storage-encryption key.

Startup behavior is explicit in the root `.env`: `AUTO_CREATE_SCHEMA`,
`ENFORCE_STRONG_SECRETS`, `ADMIN_REQUIRE_PASSWORD_TRANSPORT`, and
`ADMIN_BOOTSTRAP_TOKEN` are configured independently instead of being inferred from one environment label.

## First administrator

Set a private `ADMIN_BOOTSTRAP_TOKEN` in the root `.env`, start the stack, and open Admin Web. A
fresh database redirects to `/setup`, where the token authorizes creation of the one-time super
administrator. Remove the token and restart Admin API after setup.

For a browserless deployment, run this command from the Zhizhi repository root:

```bash
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/admin.yml" \
  uv --directory zhizhi-backend run zhizhi-admin-api init-super-admin
```

The command creates the one-time super administrator and refuses to replace an existing one. It
always reads the password from a hidden prompt and never prints it.

## Run

From the Zhizhi repository root:

```bash
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/admin.yml" \
  uv --directory zhizhi-backend run zhizhi-admin-api --host 127.0.0.1 --port 8001
```

The management console expects the service at port `8001` in local development.

With `AUTO_CREATE_SCHEMA=true`, startup creates missing Zhizhi and Gewu tables. Set it to `false`
only when another process has provisioned the complete schema.

## Focused verification

```bash
uv run pytest apps/zhizhi-admin-api/tests
uv run ruff check apps/zhizhi-admin-api
uv run mypy
```

## License

[MIT](../../LICENSE)
