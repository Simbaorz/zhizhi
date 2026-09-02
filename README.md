# Zhizhi (致知)

[简体中文](README.zh-CN.md)

> Turn enterprise knowledge into governed Agent capabilities without replacing the systems that already run the business.

## Every enterprise already knows a great deal

Policies live in documents. Operating experience lives in wikis. Procedures live in the heads of experienced employees. Definitions live in data dictionaries, while the facts needed to answer today's question live in business systems.

The usual answer is to place all of this behind a search box. Documents are split into chunks, retrieved by similarity, and handed to a model. That can be useful, but it also creates a fragile chain: structure is lost during chunking, retrieval can miss the decisive rule, and another layer of intent detection, query rewriting, and clarification is often added to compensate.

Zhizhi starts from a different premise: a reliable enterprise answer needs more than retrieval. It needs the right knowledge structure, the right live facts, the right execution context, and the right permissions to be assembled for this user, in this organization, for this conversation.

## From a question to a governed answer

When an employee asks a question, the enterprise host first authenticates the caller and supplies a trusted tenant, organization, and principal context. Zhizhi then:

1. validates the tenant and the active path through an arbitrary-depth organization tree;
2. resolves the nearest authorized model and business-data source;
3. mounts tenant and organization knowledge as a read-only workspace;
4. exposes the Scenes and Skills visible to the current scope;
5. creates an explicit, server-safe ToolSet;
6. asks [Gewu](https://github.com/Simbaorz/gewu) to run the Agent turn with persistent conversation, context, memory, and compaction support;
7. streams the answer back to the enterprise application, including clarification and interruption flows.

The result is not another isolated chatbot. It is an Agent capability that can sit behind an enterprise's existing portal, application, or workflow.

## Knowledge keeps its shape

Zhizhi does not begin by turning every document into anonymous vector fragments. Knowledge can remain in files and directories, be reviewed in Git, and be packaged with explicit meaning:

- **Scenes** organize the context for a recognizable business situation.
- **Skills** describe reusable procedures and ways of working.
- **Workspace files** preserve policies, dictionaries, explanations, and supporting material in their authored structure.
- **Data sources** provide governed access to current facts through a bounded, read-only gateway capability.

The Agent can discover and read the mounted knowledge with file tools, invoke a Skill, request clarification with `ask_user`, and query a bound data source when the answer requires live evidence. Retrieval can still be added where it helps; it is not the only organizing principle.

## Governance follows the enterprise

A tenant is the isolation boundary. Inside a tenant, organization units form a recursive tree rather than a fixed hierarchy such as region, province, city, or department.

Administrators separate two decisions:

- an **entitlement** says which resource a tenant or organization unit may use or delegate;
- a **binding** says which authorized resource is selected at that scope.

For models and data sources, resolution starts at the active organization unit and walks toward the tenant. The nearest valid binding wins. Knowledge is mounted from the tenant and the complete active organization path, so the same runtime can serve different organizations without flattening their boundaries.

## Architecture

```text
Enterprise application
  ├─ authenticates the user
  ├─ owns business authorization and product UI
  └─ sends trusted tenant / organization / principal context
                         │
                         ▼
                  Zhizhi Web API
                         │
             scope and capability resolution
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
   model binding    data-source binding   knowledge workspace
                                             │
                                      Scenes and Skills
       └─────────────────┬─────────────────┘
                         ▼
                  Gewu Agent Runtime
                         │
       conversation · context · memory · compaction · tools
```

Zhizhi is the governed enterprise application layer. Gewu remains a separate, business-neutral Agent Runtime dependency.

## Repository guide

| Project | Role | Documentation |
| --- | --- | --- |
| `zhizhi-backend` | Tenant and organization governance, Admin API, Agent Web API, persistence, resource resolution, and background jobs | [README](zhizhi-backend/README.md) · [中文](zhizhi-backend/README.zh-CN.md) |
| `zhizhi-admin-web` | Management console for organizations, models, data sources, Git knowledge, Scenes, Skills, entitlements, and bindings | [README](zhizhi-admin-web/README.md) · [中文](zhizhi-admin-web/README.zh-CN.md) |
| `zhizhi-web` | Lightweight API workbench that demonstrates how an existing enterprise UI can integrate the Agent service | [README](zhizhi-web/README.md) · [中文](zhizhi-web/README.zh-CN.md) |

The three projects share one Git history but remain independently buildable and deployable.

## Technical shape

- Python 3.12+, FastAPI, Pydantic V2, SQLAlchemy, Redis, Celery, and `uv` on the backend.
- Vue 3, TypeScript, Vite, Element Plus, Pinia, and pnpm for the management console.
- Vue 3, TypeScript, Vite, and Server-Sent Events for the integration workbench.
- Filesystem-backed managed workspaces, optional object storage for chat media, and Git-backed Scene synchronization.
- A read-only Runtime ToolSet: `list`, `read`, `glob`, `grep`, `skill`, `ask_user`, and an optional bound `query_data_source`.

## Deliberate boundaries

Zhizhi does not try to replace an enterprise identity provider, employee directory, business authorization service, or mature product UI. The included Web project is a workbench, not a complete chat product.

The first open-source release also keeps Runtime workspaces read-only and does not expose shell execution or unrestricted file mutation. It does not yet provide subagents. These constraints trade terminal-agent breadth for a smaller and more controllable server-side security surface.

## Start exploring

Requirements:

- Python 3.12 and `uv`
- Node.js 22 with Corepack
- Redis for the backend processes

The repository root is the deployment `PROJECT_HOME`. Shared backend configuration lives in
`conf/`, while `scripts/` contains cross-project development orchestration. After preparing the
backend bootstrap environment and three local YAML files as described in the
[Backend guide](zhizhi-backend/README.md), then start the complete local stack from the repository
root:

```bash
cp .env.example .env
```

```bash
./scripts/start-local.sh
```

This starts both APIs, the Worker, Admin Web, and the integration workbench.

Start with the [Backend guide](zhizhi-backend/README.md), then choose the interface you need:

- use [Admin Web](zhizhi-admin-web/README.md) to configure tenants, organizations, models, knowledge, and resources;
- use [Zhizhi Web](zhizhi-web/README.md) to observe the integration contract and streaming conversation lifecycle.

This repository is an early open-source baseline. APIs and schemas may evolve without legacy compatibility until the project declares a stable release line.

## License

[MIT](LICENSE)
