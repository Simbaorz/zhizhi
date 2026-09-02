# 致知

[简体中文](README.zh-CN.md)

致知 is an enterprise knowledge-question-answering Agent stack built on the [Gewu Agent Runtime](https://github.com/Simbaorz/gewu). It combines a governed backend, a dedicated management console, and a lightweight Web API workbench so enterprises can add Agent capabilities without replacing their existing identity system or product UI.

## Components

- `zhizhi-backend/`: tenant isolation, arbitrary-depth organizations, resource governance, Agent Web API, Admin API, persistence, and background workers.
- `zhizhi-admin-web/`: administrator console for organizations, models, data sources, Git knowledge, Scenes, Skills, entitlements, and bindings.
- `zhizhi-web/`: lightweight Web API trial client and integration reference.

All three components live in this repository and are versioned together. They remain independently buildable and deployable.

## Architecture

```text
Enterprise host application
  ├─ authentication and business authorization
  ├─ existing product UI
  └─ trusted tenant / organization / principal context
                    │
                    ▼
              致知 Web API
                    │
          capability and policy resolution
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
   Models       Data sources   Scenes / Skills
      └─────────────┼─────────────┘
                    ▼
             Gewu Agent Runtime
```

Tenant is the isolation boundary, and organization units form an arbitrary-depth tree. Entitlements define what a scope may use or delegate; bindings define what the Runtime selects. Requests resolve from the active organization unit toward its ancestors and tenant, with the nearest valid model binding winning.

Gewu remains an independent project and is not vendored into this repository. The backend locks its Gewu packages to a published Git revision until regular package releases are available.

## Development

Requirements:

- Python 3.12+
- `uv`
- Node.js 22+
- Corepack with pnpm

Install and verify each frontend application in its own directory:

```bash
cd zhizhi-admin-web
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build

cd ../zhizhi-web
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

Run `corepack pnpm run dev` inside the frontend you want to start. Admin Web uses port 5173; Web uses port 5174.

Install and verify the backend:

```bash
cd zhizhi-backend
uv sync --all-packages --all-extras --all-groups --frozen
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
```

See each component README for local configuration and startup details.

## License

Apache License 2.0. See [LICENSE](LICENSE).
