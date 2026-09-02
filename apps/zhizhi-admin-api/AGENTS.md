# 致知 Admin API Guidelines

- This app is an independently configured and deployed management API.
- Keep administrator authentication, roles, tenants, arbitrary organization units, models, Skills, Scenes, Git knowledge sources, data sources, resource entitlements, and bindings.
- Do not expose enterprise end-user login, personal workspaces, or product-facing conversation management.
- Reuse Gewu Runtime/Core packages. Management, asset, and persistence adapters belong to `zhizhi-application`.
- Use `apply_patch` for manual edits and never commit real configuration, credentials, or runtime data.
