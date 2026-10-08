# Zhizhi Web

[简体中文](README.zh-CN.md)

Test-user client for the optional Zhizhi Portal. It provides login, authorized scope selection,
a personal conversation directory, rename/archive/restore, streaming Agent responses, explicit
Scene/Skill selection, image uploads, clarification questions and run interruption/recovery.

Browser users no longer enter tenant or principal identifiers. They select an assigned scope;
Portal constructs trusted context and forwards requests to the existing Agent API. Internal
Runtime meta messages are hidden by type, tools are merged into expandable summaries, and
clarification history is retained. Reloading the page does not interrupt a persisted run.

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm run dev
```

Open http://127.0.0.1:5174. The Vite /api proxy targets Portal at http://127.0.0.1:8003;
use ZHIZHI_PORTAL_API_PROXY_TARGET to override. For same-origin deployment no API base is
needed; VITE_ZHIZHI_API_BASE_URL may select a separately deployed Portal origin with an
appropriate reverse proxy and cookie setup. Portal and this UI should normally share an origin.

Use Portal Admin at http://127.0.0.1:5175 to create test users and assign tenant-root or any
organization scopes. The existing main Admin continues to govern models, knowledge and data
sources. No business-specific province/city model is assumed.

This Portal is a TEST host, not an enterprise identity provider. Production applications own
end-user authentication and authorization and independently call the Agent Web API with
conversation_id, tenant_code, optional active_organization_unit_id, principal_id and principal_type.
See ../zhizhi-backend/README.md and ../zhizhi-backend/apps/zhizhi-portal-api/README.md.

```bash
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run build
```
