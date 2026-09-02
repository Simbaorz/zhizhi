# Zhizhi Admin Web

[简体中文](README.zh-CN.md) · [Back to the project overview](../README.md)

An enterprise Agent does not become trustworthy because it has a better chat box. Someone must decide which organization may use which model, which knowledge is authoritative, where live facts come from, and who is allowed to change those decisions.

Zhizhi Admin Web is that control surface.

It is a dedicated management console for the Zhizhi Admin API. It turns the backend's tenant, organization, resource, knowledge, and administrator policies into visible workflows without mixing them into the end-user Agent experience.

## The administrator's story

A platform administrator can create the global resource catalog and delegate resources to tenants. A tenant administrator can then work within the scopes and permissions assigned to that tenant.

Inside the console, an administrator can:

1. create tenants and an arbitrary-depth organization tree;
2. create or bind administrator accounts and assign roles;
3. configure model providers, credentials, capabilities, and connectivity;
4. grant model and data-source entitlements to a tenant or organization unit;
5. bind the effective model or data source at a selected scope;
6. register Git repositories and authorize them for tenants;
7. create, edit, upload, package, and synchronize Scenes and Skills;
8. inspect only the navigation and actions allowed by the current RBAC session.

The console distinguishes **available resources** from **bound resources**. Availability controls what a scope may use or delegate; binding controls what execution selects. This distinction is the center of the management experience, not an implementation detail hidden in the API.

## What the console manages

| Area | Current capabilities |
| --- | --- |
| Global management | Platform-wide resource and tenant administration for super administrators |
| Organizations | Tenants and recursive organization units without fixed depth |
| Accounts and roles | Administrator accounts, tenant memberships, roles, permissions, and password reset |
| Models | Provider configuration, encrypted credentials, validation, test calls, entitlements, and bindings |
| Data sources | HTTP gateway configuration, encrypted credentials, entitlements, and bindings |
| Git knowledge | Repository registration, credential updates, connectivity tests, and tenant entitlements |
| Scenes | File editing, directory operations, package upload/download, Git association, manual sync, and sync history |
| Skills | `SKILL.md`-based asset creation, file editing, package import/export, and manifest-aware updates |

This project does not manage enterprise employees, end-user login, business permissions, or product-facing conversations. Those remain responsibilities of the host system.

## Session and API boundary

Zhizhi Admin Web uses the Admin API's administrator session and permission-aware navigation. Passwords are encrypted in the browser with the Admin API's RSA public key before transport. Requests use same-origin `/api` paths by default.

For local development, Vite proxies `/api` to:

```text
http://127.0.0.1:8001
```

Override the target with `ZHIZHI_ADMIN_API_PROXY_TARGET`.

The first super administrator is created from the Zhizhi repository root:

```bash
PROJECT_HOME="$PWD" CONFIG_FILE="$PWD/conf/admin.yml" \
  uv --directory zhizhi-backend run zhizhi-admin-api init-super-admin
```

See the [Backend guide](../zhizhi-backend/README.md) for configuration and startup.

## Technology

- Vue 3 with the Composition API
- TypeScript
- Vue Router
- Pinia
- Element Plus
- CodeMirror and Markdown editing support
- Tailwind CSS through the Vite plugin
- Vite and Vitest

The interface uses the Zhizhi blue-violet visual system and assets under `src/assets`.

## Development

Requirements:

- Node.js 22+
- Corepack

Install the dependencies locked for this project:

```bash
corepack pnpm install --frozen-lockfile
```

Start the development server:

```bash
corepack pnpm run dev
```

Open `http://127.0.0.1:5173`.

To target another Admin API:

```bash
ZHIZHI_ADMIN_API_PROXY_TARGET=http://127.0.0.1:9001 corepack pnpm run dev
```

## Verification and build

```bash
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

The production output is written to `dist/`. A production deployment should serve the static files behind the same trusted origin or reverse proxy as the Admin API.

## License

[MIT](LICENSE)
