# 致知 Backend Monorepo Guidelines

This repository is the business-neutral host application for the Gewu Agent Runtime and is built as a Python `uv workspace`.

## Workspace

- `packages/zhizhi-application/`: Identity context, organization scopes, models, data sources, workspaces, Skills, Scenes, audit, and persistence adapters.
- `apps/zhizhi-web-api/`: Minimal enterprise integration API and Agent Runtime composition root.
- `apps/zhizhi-admin-api/`: Management API and administrator IAM composition root.
- `apps/zhizhi-worker/`: Background jobs and scheduler composition root.

## Boundaries

- 致知 depends on Gewu; business rules must not be added to Gewu.
- The Web API does not own enterprise end-user login, password, profile, or conversation-list products.
- Tenant is the isolation boundary. Organization units form an arbitrary-depth tree and must never encode fixed region levels.
- Resource entitlements define what a scope may bind or delegate. Runtime bindings resolve through the active organization path.
- Model bindings use nearest-ancestor fallback. Scene, Skill, knowledge, file, data-source, and Tool bindings compose as authorized collections.
- Runtime workspaces are read-only and ToolSets use explicit allowlists. Do not expose shell or file-mutation tools.
- Credentials are resolved server-side and never returned to Runtime callers.

## Working Principles

- Think Before Coding: State assumptions, ambiguities, and tradeoffs before making changes.
- Simplicity First: Use the smallest design and least code that solve the current requirement.
- Surgical Changes: Do not refactor, reformat, or optimize unrelated code.
- Goal-Driven Execution: Add tests for new behavior and verify the relevant outcomes.
- No Legacy Compatibility: Do not retain obsolete schemas or contracts unless migration is explicitly requested.

## Development

- Python 3.12 is the minimum supported version; data contracts use Pydantic V2.
- Use `apply_patch` for manual edits.
- Do not read or commit real credentials, runtime configuration, generated output, or unrelated lock-file changes.

## Verification

```bash
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
```
