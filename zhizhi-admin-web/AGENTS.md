# 致知 Admin Web Guidelines

- This package is the independently built and deployed 致知 management console.
- Preserve administrator authentication, roles, tenants, arbitrary organization units, models, Git knowledge sources, data sources, Skills, Scenes, resource entitlements, and bindings.
- Do not add enterprise end-user login, personal workspaces, or product-facing conversation management.
- Use Vue 3 Composition API, TypeScript, Pinia, Vue Router, Element Plus, and pnpm.
- Use the shared blue-violet design tokens and generated 致知 brand assets; do not reintroduce legacy green branding.
- Keep components focused and reuse established form, panel, table, tree, and feedback primitives.
- Use `apply_patch` for manual edits.
- Run `corepack pnpm test`, `corepack pnpm run typecheck`, and `corepack pnpm run build` from this package directory after relevant changes.
