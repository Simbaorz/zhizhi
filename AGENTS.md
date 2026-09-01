# Zhizhi Web Guidelines

- This repository is a lightweight trial and integration-reference client for the Zhizhi Web API.
- Keep only session context, streaming chat, current-conversation recovery, Scene/Skill invocation, `ask_user` continuation, attachment support, and interrupt.
- Do not add login, user administration, conversation lists, resource management, or personal workspaces.
- Use Vue 3 Composition API, TypeScript, Element Plus, and pnpm.
- Use the shared blue-violet design tokens and generated Zhizhi brand assets; do not reintroduce legacy green branding.
- Keep API text and controls code-native, responsive, accessible, and suitable as integration examples.
- Use `apply_patch` for manual edits.
- Run `pnpm test`, `pnpm typecheck`, and `pnpm build` after relevant changes.
