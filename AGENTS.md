# Zhizhi Admin Web Guidelines

- This repository is the independently built and deployed Zhizhi management console.
- Preserve administrator authentication, roles, tenants, arbitrary organization units, models, Git knowledge sources, data sources, Skills, Scenes, resource entitlements, and bindings.
- Do not add enterprise end-user login, personal workspaces, or product-facing conversation management.
- Use Vue 3 Composition API, TypeScript, Pinia, Vue Router, Element Plus, and pnpm.
- Use the shared blue-violet design tokens and generated Zhizhi brand assets; do not reintroduce legacy green branding.
- Keep components focused and reuse established form, panel, table, tree, and feedback primitives.
- Use `apply_patch` for manual edits.
- Run `pnpm test`, `pnpm typecheck`, and `pnpm build` after relevant changes.
