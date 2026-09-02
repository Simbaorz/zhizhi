# 致知 Web

[简体中文](README.zh-CN.md)

致知 Web is a lightweight trial client and integration reference for the 致知 Agent Web API. It demonstrates trusted session context, streaming responses, Scene and Skill invocation, image attachments, `ask_user` continuation, current-conversation recovery, and interrupt.

It is intentionally not a complete enterprise chat product: there is no login, user management, conversation list, or resource administration. Production systems can copy the API interaction patterns while keeping their existing identity and product UI.

## Development

Run from this directory:

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run dev
```

The development server runs on `http://127.0.0.1:5174` and proxies `/api` to `http://127.0.0.1:8000`.

```bash
ZHIZHI_API_PROXY_TARGET=http://127.0.0.1:8080 corepack pnpm run dev
```

For a cross-origin production deployment, set `VITE_ZHIZHI_API_BASE_URL` during the build. Same-origin deployments need no value.

The trial session context is kept in `sessionStorage`. It contains `conversation_id`, `tenant_id`, optional `active_organization_unit_id`, `principal_id`, and `principal_type`. The host application is responsible for authenticating the user before supplying these values.

## Production build

```bash
corepack pnpm run build
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
