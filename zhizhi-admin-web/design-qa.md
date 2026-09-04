# Organization Management Design QA

## Comparison target

- Source visual truth: `/var/folders/c4/xy4q5yrs2pg3jryjdwkyyphh0000gp/T/codex-clipboard-b5a77dd8-c39b-47d0-83ca-23756c2a3dd7.png`
- Source pixels: 2488 × 982.
- Implementation route: `http://127.0.0.1:5174/global`.
- Source state: one root organization row with the redundant selected-row detail card expanded.

## Finding and fix

- P1 — The expanded detail card repeated type, external key, status, and actions already present in the table row. It added a large violet block, broke table rhythm, and made an accidental row click feel like navigation.
- Fix — Removed the hidden detail expander, active-row state, row-click behavior, repeated detail markup, and all related styles.
- Resulting interaction — Rows remain stable. Only the hierarchy arrow expands or collapses child organizations; add-child, edit, and delete remain explicit row actions.

## Automated verification

- Organization layout regression tests: passed.
- Vitest suite: passed.
- Vue TypeScript check: passed.
- Vite production build: passed.
- Git diff whitespace validation: passed.
- Local preview HTTP availability: passed.

## Visual comparison blocker

The required Browser runtime is not callable in this session. The updated preview was opened in the Codex browser panel, but an implementation screenshot and same-viewport comparison could not be captured. No browser-rendered visual pass is claimed.

final result: blocked
