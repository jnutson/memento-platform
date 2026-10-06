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
daemon, wrapper, model subprocess, or retry loop. See
[user-invoked review](../../tools/review/README.md).

## Production boundary

The operator checks the product and approves merge. CI is the shared full gate.
For a hard merge gate on `main`, use a GitHub plan that enforces protection on this
private repo; target `main`, require a PR and the `Verify / Verify` status check,
and disallow bypass/direct pushes (including the owner). Do not require a second
human approval for the solo operator. Confirm the rule is *active* and actually
targets `main` with a disposable PR before relying on it. This protects CI/PR
review; it does not turn a local skill invocation into a required GitHub check.
The operator separately approves production migration and deployment. All Vercel
deployments for this repo are manual: `apps/web/vercel.json` sets
`git.deploymentEnabled` to `false`, so a push or merge must not create a Preview or
Production deployment. To request a Preview, run `vercel deploy` from the linked
`apps/web` project checkout; to release an approved `main` commit after any approved
production migration, run `vercel deploy --prod` from that checkout. Confirm the
deployment's commit and target in Vercel before smoke testing. Before the manual
release, fetch `origin/main`, check out the approved main commit in a clean linked
worktree, and run `make release-commit-check APPROVED_SHA=<full-approved-commit-sha>`.
This is only a local identity check: it compares HEAD, the supplied approved SHA,
and fetched `origin/main`. It does not establish READY/review history, grant release
approval, prove that the remote ref is fresh, or prove what Vercel deployed. Confirm
the draft PR's READY evidence, any explicitly requested review, and approved merge
before this step; obtain
separate operator deployment approval, then verify the remote main SHA and resulting
Vercel deployment identity. Never make the manual
deployment a push-triggered CI job. Do not treat repository commands as evidence of
GitHub branch protection or live Vercel settings; verify that the first push with
this configuration produced no automatic deployment before relying on it.
After an approved deployment, use an existing Access session in
`MEMENTO_SMOKE_COOKIE` or `MEMENTO_SMOKE_AUTHORIZATION` and run:

```bash
make smoke-production BASE_URL=https://protected.example \
  ORIGIN_URL=https://direct-origin.example DEPLOYMENT_ID=<id> \
  DB_ROUTE=/attention FEATURE_ROUTE=/new-feature APP_MARKER=Memento
```

Use actual deployed values, not the placeholders. The command follows no redirect,
tests direct-origin denial and authenticated app/DB/feature reads, and writes ignored
`.memento/delivery/smoke.json`. It stores statuses and rollback advice, never response
bodies or session secrets. On failure, hold rollout and ask for rollback approval;
the command cannot roll back.
