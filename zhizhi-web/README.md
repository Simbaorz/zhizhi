# Zhizhi Web

[简体中文](README.zh-CN.md) · [Back to the project overview](../README.md)

The shortest path to adopting an Agent is often not a new product. It is a clear API contract that an existing product can understand.

Zhizhi Web is a small, runnable explanation of that contract. It lets a developer enter a trusted session context, start a streaming Agent turn, invoke a Scene or Skill, upload an image, answer a clarification request, recover the current conversation, and interrupt a run.

It is deliberately a workbench rather than a complete enterprise chat application.

## The integration story

A typical host application already knows who the user is and where the conversation belongs. It supplies that context to Zhizhi and keeps ownership of the surrounding product experience.

```text
existing enterprise UI
        │
        ├─ conversation and message composer
        ├─ authenticated user and organization context
        └─ product-specific business workflow
        │
        ▼
Zhizhi Agent Web API
        │
        ├─ capability discovery
        ├─ SSE conversation stream
        ├─ Scene and Skill invocation
        ├─ image attachment lifecycle
        ├─ ask_user continuation
        ├─ message and pending-state recovery
        └─ interrupt
```

Zhizhi Web demonstrates the right-hand side of that boundary. A production application should reuse the interaction pattern, not necessarily this interface.

## What the workbench demonstrates

- editing and persisting a temporary caller context in `sessionStorage`;
- loading the effective capabilities for that context;
- listing visible Scenes and Skills;
- starting an idempotent Agent request and parsing Server-Sent Events;
- rendering assistant, Tool use, Tool result, and clarification messages;
- uploading images before a turn and resolving authorized attachment URLs;
- resuming a pending `ask_user` interaction;
- recovering persisted messages and pending state for the current conversation;
- requesting interruption of the active run.

There is intentionally no login page, employee directory, tenant administration, resource configuration, or conversation list.

## Trusted caller context

The workbench sends these values with Agent requests:

| Field | Meaning |
| --- | --- |
| `conversation_id` | Host-owned identifier for the current conversation |
| `tenant_id` | Zhizhi tenant isolation boundary |
| `active_organization_unit_id` | Optional active organization node; empty means tenant-level |
| `principal_id` | Host-owned caller identifier |
| `principal_type` | Caller kind, `user` by default |

The values stored by this demo are editable browser state. They are not proof of identity.

Do not expose the Agent API publicly and trust these fields directly. In production, the enterprise host or gateway must authenticate the user, enforce business authorization, and construct or validate the context before forwarding the request to Zhizhi.

## API calls used by the client

| Method | Path |
| --- | --- |
| `GET` | `/api/agent/capabilities` |
| `GET` | `/api/agent/skills` |
| `GET` | `/api/agent/scenes` |
| `POST` | `/api/agent/chat/stream` |
| `POST` | `/api/agent/chat/ask-answer` |
| `POST` | `/api/agent/chat/attachments` |
| `GET` | `/api/agent/chat/attachments/{attachment_id}` |
| `GET` | `/api/agent/conversations/{conversation_id}/messages` |
| `GET` | `/api/agent/conversations/{conversation_id}/pending-ask` |
| `POST` | `/api/agent/conversations/{conversation_id}/interrupt` |

See the [Backend guide](../zhizhi-backend/README.md) for the complete service contract and configuration model.

## Technology

- Vue 3 Composition API
- TypeScript
- Vite
- Element Plus
- Markdown rendering with DOMPurify sanitization
- Native `fetch` and Server-Sent Event frame parsing
- Node's built-in test runner

The project remains intentionally small so its API interactions are easy to trace and copy.

## Development

Requirements:

- Node.js 22+
- Corepack
- Zhizhi Web API running locally or at a reachable URL

Install this project's locked dependencies:

```bash
corepack pnpm install --frozen-lockfile
```

Start the development server:

```bash
corepack pnpm run dev
```

Open `http://127.0.0.1:5174`. Vite proxies `/api` to `http://127.0.0.1:8000` by default.

Use another local API:

```bash
ZHIZHI_API_PROXY_TARGET=http://127.0.0.1:8080 corepack pnpm run dev
```

## Production build

For a same-origin deployment, no API base value is required. For a cross-origin static deployment, provide the API origin at build time:

```bash
VITE_ZHIZHI_API_BASE_URL=https://agent.example.com corepack pnpm run build
```

The output is written to `dist/`.

## Verification

```bash
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

## License

[MIT](LICENSE)
