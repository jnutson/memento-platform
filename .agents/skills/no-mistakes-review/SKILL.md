---
name: no-mistakes-review
description: Perform an independent findings-first review. Use only when the user explicitly invokes $no-mistakes-review.
---

# No Mistakes review

Review the requested branch, commit, or working-tree change without editing it. Confirm
the target and intent from context; ask only if the target is ambiguous. Inspect repository
rules, the diff, affected contracts, tests, and verification evidence.

Prioritize:

1. Incorrect behavior or mismatch with accepted intent.
2. Data leakage, unsafe trust-boundary crossings, or destructive behavior.
3. Loss of lineage, determinism, reproducibility, or idempotent rerun behavior.
4. Missing validation and meaningful regression coverage.
5. Unnecessary complexity that makes future retailer adapters unsafe or coupled.

Run only non-mutating checks unless the user separately authorizes artifact-producing
verification. Never load secrets or raw customer data into review context. Do not edit,
commit, push, open a PR, deploy, or silently repair findings.

Report findings first, ordered by severity, with exact file and line references. Then
state reviewed revision/scope, checks actually completed, unrun checks, and remaining
risks. Say explicitly when no findings are present; do not manufacture them.
