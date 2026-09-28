---
name: planner
description: Produce and save a bounded Markdown builder handoff without changing implementation. Use only when the user explicitly invokes $planner.
---

# Planner

Inspect relevant code, tests, data contracts, and architecture. Optimize for the
smallest working product loop and preserve the trust and classification rules.

Planning is implementation-read-only: do not change product code, tests, configuration,
schemas, data, databases, branches, or external state. You may create or update only the
Markdown plan requested by the user, normally beneath `docs/plans/`. If no plan path is
specified, choose a concise lowercase kebab-case filename and report it.

Return a compact handoff with:

1. Outcome and non-goals.
2. Expected files and boundaries to change.
3. Acceptance checks and the narrowest useful verification.
4. Data classifications, fixtures, and lineage assumptions.
5. Irreversible, external, production, or destructive decisions requiring approval.

Do not implement, create a branch, mutate data, or expand authority from the plan. Keep
the plan file limited to planning content; do not embed generated data or sensitive
payloads. Inspect the resulting diff to confirm that only the intended Markdown plan
changed, apart from an explicitly requested update to this workflow itself.
End with `Builder handoff`, a lowercase kebab-case task name, the outcome, acceptance
checks, and review intent.
