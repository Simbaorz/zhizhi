# 致知 Monorepo Guidelines

This repository contains the complete 致知 enterprise knowledge Agent application built on Gewu.

## Workspace

- `zhizhi-backend/`: Python `uv workspace` for the application layer, Web API, Admin API, and Worker.
- `zhizhi-admin-web/`: Vue management console.
- `zhizhi-web/`: Vue Web API trial workbench.
- `gewu/`, when present locally, is an ignored independent checkout and must not be committed here.

This is one Git repository. Do not create nested repositories or commit dependency caches, generated output, credentials, real configuration, or runtime data.

## Boundaries

- 致知 may depend on Gewu. Gewu must never depend on 致知.
- The enterprise host owns end-user authentication, product UI, and business authorization.
- 致知 owns Agent capability configuration, resource allocation, Runtime composition, and management workflows.
- Backend, Admin Web, and Web remain independently buildable even though they are versioned together.

## Working Principles

- Think Before Coding: State assumptions, ambiguities, and tradeoffs before making changes.
- Simplicity First: Use the smallest design that solves the current requirement.
- Surgical Changes: Do not refactor or reformat unrelated code.
- Goal-Driven Execution: Translate changes into verifiable outcomes and test new behavior.
- No Legacy Compatibility: Do not preserve obsolete schemas or contracts unless a migration is explicitly requested.

## Verification

Run frontend checks from the repository root:

```bash
corepack pnpm run test
corepack pnpm run typecheck
corepack pnpm run build
```

Run backend checks from `zhizhi-backend/`:

```bash
uv run black apps packages --check
uv run ruff check apps packages
uv run mypy
uv run pytest
uv lock --check
```
