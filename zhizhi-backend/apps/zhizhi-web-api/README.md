# Zhizhi Web API

[Back to Zhizhi Backend](../../README.md)

The Web API is the integration-facing process that turns a trusted enterprise context into a streaming Agent conversation.

It intentionally exposes a small surface. The enterprise host authenticates the user, enforces business authorization, and supplies the tenant, active organization unit, principal, and conversation identifiers. The Web API validates the Zhizhi scope, resolves effective capabilities, and delegates the turn to Gewu.

## Request lifecycle

For each turn, the process:

1. validates the trusted caller context and request limits;
2. resolves the active organization path;
3. chooses the nearest model and data-source bindings;
4. mounts the tenant and organization Workspace roots read-only;
5. exposes visible Scenes, Skills, and the bounded ToolSet;
6. starts or resumes a Gewu run;
7. streams normalized Server-Sent Events and persists conversation state.

`request_id` is the idempotency key. Reusing it for different input returns a conflict.

## HTTP surface

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
- `GET /healthz`
- `GET /readyz`

The chat and clarification endpoints return `text/event-stream`. Stream events include the run, request, and conversation correlation identifiers.

## Security boundary

The process is not an identity provider. Context fields supplied by a browser are not inherently trusted. Deploy it behind an authenticated enterprise application or gateway and validate that callers cannot forge another tenant, organization, or principal.

Runtime Workspace access is read-only. The ToolSet contains file discovery/read tools, Skill loading, `ask_user`, and an optional authorized data-source query tool; it contains no shell.

## Configuration

The default local configuration is `conf/web.yml`, created from `conf/web.example.yml` at the Zhizhi repository root.

The process requires:

- database and Redis connectivity;
- a non-empty Workspace storage root;
- local media storage or configured object storage;
- the same storage-encryption key used by Admin API and Worker;
- Agent concurrency, timeout, compaction, and image-admission limits;
- outbound HTTP and data-source result limits.

## Run

From the Zhizhi repository root:

```bash
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/web.yml" \
  uv --directory zhizhi-backend run zhizhi-web-api --host 127.0.0.1 --port 8000
```

Check process and Runtime state:

```bash
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/readyz
```

## Focused verification

```bash
uv run pytest apps/zhizhi-web-api/tests
uv run ruff check apps/zhizhi-web-api
uv run mypy
```

## License

[MIT](../../LICENSE)
