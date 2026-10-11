---
name: builder
description: Implement an accepted handoff and verify the result. Use only when the user explicitly invokes $builder.
---

# Builder

Implement the accepted scope end to end. Confirm the effective write permission and
work from a clean named `codex/<task-name>` branch or isolated worktree when available.
Preserve unrelated changes.

Build the thinnest coherent solution. Enforce data contracts at boundaries, use only
synthetic minimized fixtures, keep source inputs immutable, and keep retailer-specific
knowledge out of canonical and metric interfaces.

Run focused checks while iterating and the applicable repository gate before completion.
Inspect the diff and Git status for unrelated edits, secrets, data files, database files,
and generated artifacts. Do not claim a check passed if it was skipped or unavailable.

Stop at the conditions in `AGENTS.md`. In particular, do not ingest real customer data,
deploy, migrate production, publish, or perform destructive actions without approval.

Report the implemented outcome, files changed, checks run and results, unrun checks,
and any remaining data or production decision. Review is a separate
`$reviewer` invocation unless the accepted handoff explicitly requires it.
