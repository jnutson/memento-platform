---
document_id: RUNBOOK-AGENT-DELIVERY
document_type: runbook
maintenance: maintained
owner: Josh Nutson
sensitivity: internal
---

# Agent delivery handoff

For pre-planning questions, invoke `$explorer` in a read-only task. It inspects and
answers without creating artifacts. Trusted-project Codex tasks default to the
`:read-only` profile; confirm it is effective for that task. Use a fresh task with
`:workspace` permission for an accepted `$builder` handoff. `$planner` begins the
planning handoff. Project config requires trusting the repo and can be overridden
by a higher-priority task setting, so the skill alone is not a sandbox.

The planner captures outcome and acceptance checks. The builder works on a named
`codex/<task>` branch in an isolated worktree, commits the slice, and leaves the tree
clean. `AGENTS.md` defines the authority boundaries.

## Before draft PR handoff

```bash
git fetch origin main
make delivery-ready VERIFICATION=no-db
# Use VERIFICATION=full for any application or database path.
make delivery-pr-check
```

`delivery-ready` writes ignored `.memento/delivery/readiness.json` and `handoff.md`.
The handoff is suitable for a PR description; it is not permission to merge. A
migration requires `MEMENTO_ENV=local` and `DATABASE_URL` for the disposable
Docker operator database. The readiness check refuses a different loopback
database or any remote target.
The command reads `alembic_version`; it never migrates. Environment-file changes
require `ACTIVATION_NOTE` with variable names and actions, never secret values.

`delivery-pr-check` fails closed unless this clean, linked task worktree has a
matching READY receipt for its branch and exact HEAD. It does not publish, review,
or change GitHub state. After it passes, the builder may push the task branch and
open or update a draft PR using the handoff. Do not push a stale receipt or treat a
draft PR as merge approval.

Review is a separate operator action. Invoke `$reviewer` explicitly when
an independent review-and-correction pass is wanted. The reviewer owns concrete
findings, associated fixes, re-review, and verification. The builder does not conduct
self-review, start, queue, or wait for review. The review skill does not launch a
daemon, wrapper, model subprocess, or retry loop.

## Production boundary

The operator checks the product and approves merge. CI is the shared full gate.
For a hard merge gate on `main`, use a GitHub plan that enforces protection on this
private repo; target `main`, require a PR and the `Verify / Verify` status check,
and disallow bypass/direct pushes (including the owner). Do not require a second
human approval for the solo operator. Confirm the rule is *active* and actually
targets `main` with a disposable PR before relying on it. This protects CI/PR
review; it does not turn a local skill invocation into a required GitHub check.
The operator separately approves any production migration or deployment. This
repository currently has no deployable frontend and no automated production-release
workflow; the supported demo surface is the local read-only API.
