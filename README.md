# 致知 Admin Web

[简体中文](README.zh-CN.md)

致知 Admin Web is the management console for the 致知 enterprise knowledge Agent stack. It provides administrator login and RBAC, tenant and arbitrary-depth organization management, model and data-source entitlements and bindings, Git knowledge sources, Scenes, Skills, and audited configuration workflows.

The console manages Agent infrastructure. It intentionally does not replace an enterprise's end-user portal, employee directory, or product-facing conversation UI.

## Organization-aware governance

Tenant is the isolation boundary. Organization units form a recursive tree and may represent any structure the enterprise chooses. Resource pages distinguish:

- Available resources that a scope may use or delegate.
- Bound resources selected for execution at that scope.

The UI uses a blue-violet visual system and the 致知 brand assets under `src/assets`.

## Development

```bash
corepack pnpm install
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run dev
```

The development server runs on `http://127.0.0.1:5173` and proxies `/api` to `http://127.0.0.1:8001`. Set `ZHIZHI_ADMIN_API_PROXY_TARGET` to use another Admin API origin.

## Production build

```bash
corepack pnpm run build
```

The static output is written to `dist/`.

## License

Apache License 2.0. See [LICENSE](LICENSE).
