# Memento Analytics Demo — Agent Rules

## Mission

Build the smallest credible demo of Memento Loop's retail analytics product while
keeping the path from synthetic data to real customer data safe and portable.

Current product boundary:

`retailer and internal inputs -> validation -> canonical retail data -> deterministic metrics`

The immediate implementation milestone is ingestion and canonicalization. Do not
build the ingestion pipeline until a task explicitly asks for it.

## Operating rules

- Treat `/Users/mininutson/Desktop/Synthetic Data` as strictly read-only from this
  repository. Never edit its code, tests, configuration, manifests, generated data,
  dependency files, or patched copies, including for cross-repository compatibility
  checks or temporary workarounds. Inspect it only. If work would require a Synthetic
  Data change, report the required change and stop; do not implement it. That
  repository's `AGENTS.md` is the sole exception when the user explicitly asks to
  update agent rules.
- Optimize for an MVP and short learning loops; avoid speculative platforms and abstractions.
- Keep validation, canonicalization, and metric logic deterministic and testable.
- Treat all source data as untrusted. Validate schemas, types, ranges, identifiers,
  dates, and file paths at system boundaries.
- Preserve source lineage and ingestion metadata without copying sensitive payloads
  into logs, exceptions, fixtures, or model context.
- DuckDB over Parquet is the analytics engine. If a persistent local operational
  database is later approved, Docker is its boundary. Do not introduce another
  database or analytics engine without approval.
- Keep raw, canonical, and derived data physically and logically distinct.
- Never mutate source extracts. Derived outputs must be reproducible from declared inputs.
- Use synthetic, minimized fixtures in tests. Never commit customer or production data.
- Keep secrets in ignored environment files or a secret manager; commit only safe examples.
- Prefer boring, explicit modules with narrow interfaces. Add a dependency only for a
  current requirement.
- Preserve unrelated work. Report checks that were not run; never claim they passed.

## Stop and ask

Stop before:

- ingesting, copying, deleting, or modifying real customer or production data;
- committing data whose classification or provenance is uncertain;
- placing secrets, credentials, sensitive records, or raw payloads in source control,
  model context, logs, fixtures, or client-visible code;
- destructive or irreversible database, filesystem, or Git operations;
- production deploys, migrations, access-control changes, paid services, or externally
  visible actions;
- weakening validation, security controls, or tests to make a check pass;
- changing the approved product scope or adding a new persistent datastore.

If a local source-data path is missing or ambiguous, inspect read-only locations when
possible; otherwise ask for the exact path. Do not search broadly through personal files.

## Repository layout

- `.agents/skills/` — explicitly invoked delivery workflows
- `docs/architecture/` — system boundaries and durable design constraints
- `src/` — product code (when implementation begins)
- `tests/` — tests and synthetic fixtures (when implementation begins)
- `data/` — ignored local inputs and generated artifacts; never a source-control data store

## Delivery workflow

The `$questions`, `$planner`, `$builder`, and `$reviewer` skills are
user-invoked only. A normal question, plan, implementation, or review request does not
implicitly invoke them.

- `$questions`: read-only discovery; no files or state changed.
- `$planner`: read-only scope and acceptance criteria ending in a builder handoff.
- `$builder`: implement accepted scope, verify it, and report evidence.
- `$reviewer`: independently reviews the change, fixes concrete in-scope issues, and
  verifies the corrected result.

Planning does not implement. Building does not redefine the product outcome. Review
does not redefine scope. A later workflow begins only when the user invokes it.

## Completion standard

A change is complete when its accepted behavior works, relevant tests/checks pass,
the diff is limited to intended files, sensitive data is absent, and remaining risks
or unrun checks are stated plainly.
