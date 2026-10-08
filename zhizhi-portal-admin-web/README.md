# Zhizhi Portal Admin

Independent Vue application for managing **test accounts**, separate from resource management
in `zhizhi-admin-web`. Sign in with an enabled platform Super Admin account. Ordinary platform
administrators cannot sign in here; no extra administrator password store is created.

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm run dev
```

Local UI: `http://127.0.0.1:5175`. `/api` proxies to Portal at `http://127.0.0.1:8003`;
override with `ZHIZHI_PORTAL_API_PROXY_TARGET`. The root local launcher starts both.

Create/edit/disable test accounts, reset their password and assign tenant roots or any valid
organization node. The UI uses centered forms and the main Admin's table and pagination style.
Platform tenants, organizations, resources and Super Admin accounts are read-only dependencies.

```bash
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```

Production enterprise hosts continue to use their own identity systems. Deploy this optional
account management tool only with the test Portal and route its same-origin `/api` to Portal.
