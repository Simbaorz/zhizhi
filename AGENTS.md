# Zhizhi Repository Instructions

## Working Principles

- Think Before Coding: Before making changes, state the relevant assumptions, ambiguities, and tradeoffs. If missing context could materially change the result, ask instead of guessing.
- Simplicity First: Use the smallest design and least code that solve the current requirement. Do not add abstractions, configuration, frameworks, or extension points for hypothetical needs.
- Surgical Changes: Change only what is required to achieve the requested outcome. Do not refactor, reformat, remove comments, or optimize unrelated code.
- Goal-Driven Execution: Translate the request into observable, verifiable outcomes. When behavior can be reproduced in a test, add or update that test before changing the implementation, then run the relevant checks.
- No Legacy Compatibility: Do not preserve obsolete logic, data structures, database schemas, or API contracts. Ignore old data unless an explicit migration or cutover is requested.

## Repository Model

This is one Git repository containing three independently buildable and deployable projects:

- `zhizhi-backend/`: Python `uv workspace` containing the application layer, Web API, Admin API, and Worker.
- `zhizhi-admin-web/`: Vue management console for platform and tenant administrators.
- `zhizhi-web/`: Lightweight Web API trial client and enterprise integration reference.

The repository root is not a Node.js workspace. It must not contain a root `package.json`, `pnpm-lock.yaml`, or `pnpm-workspace.yaml`. Each frontend owns its package manifest, lockfile, package-manager version, commands, and dependency installation.

Do not create nested Git repositories. Do not commit dependency directories, virtual environments, build output, caches, credentials, real environment files, local databases, logs, or runtime data.

## Architecture Boundaries

- Zhizhi may depend on Gewu. Gewu must never depend on Zhizhi.
- Gewu is an external Agent Runtime dependency and must not be copied or vendored into this repository.
- The enterprise host application owns end-user authentication, business authorization, user-facing product flows, and the trusted tenant, organization, and principal context.
- Zhizhi owns Agent capability configuration, resource governance, Runtime composition, persistence, management workflows, and the integration-facing Agent APIs.
- `zhizhi-web` is a trial client and reference implementation. Do not turn it into a complete enterprise chat product, identity system, or administration console.
- `zhizhi-admin-web` is the management console. Do not add end-user product flows to it.

## Domain Invariants

- Tenant is the isolation boundary. Every tenant-owned record and operation must remain tenant-scoped.
- Organization units form an arbitrary-depth tree. Never encode fixed geographic or organizational levels.
- Principals and groups may belong to organization units without changing the organization-tree model.
- Resource entitlements define what a scope may use or delegate. Resource bindings define what is selected for execution.
- Model and data-source selection use the nearest valid binding while walking from the active organization unit toward its ancestors and tenant.
- Runtime knowledge composes the tenant Workspace with every organization Workspace on the active path. Managed Scenes and Skills are tenant-scoped in the current release.
- Credentials are resolved on the server and must never be returned to Runtime callers or frontend clients.
- Runtime workspaces are read-only, and ToolSets use explicit allowlists. Do not expose shell execution or unrestricted file mutation.

## Change Discipline

- Preserve unrelated user changes and keep each commit focused on one coherent outcome.
- Use `apply_patch` for manual edits. Do not edit generated files directly.
- Update a lockfile only when its owning project's dependency metadata changes.
- Keep source code, comments, documentation, package names, and user-facing terminology aligned with Zhizhi. Do not leave references to source projects or internal-only infrastructure.
- Never read, print, copy, or commit real credentials or local configuration.
- Add dependencies only when the requirement cannot be met clearly with the existing stack.

## Verification

Run checks only for the projects affected by the change. Run all three project suites for cross-cutting changes.

From `zhizhi-admin-web/`:

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

From `zhizhi-web/`:

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

From `zhizhi-backend/`:

```bash
uv sync --all-packages --all-extras --all-groups --frozen
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
```

Before finishing, run `git diff --check` and confirm that no generated, credential, or runtime files are included in the change.
