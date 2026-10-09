# Trust Boundaries

Status: initial MVP outline. Update this document as concrete interfaces are chosen.

## Users and systems

- **Memento operator/developer:** runs local ingestion, validation, and analysis.
- **CPG customer users (future):** provide data and consume insights; customer isolation
  and authorization requirements are not yet designed.
- **Retailer and internal sources:** POS, inventory, in-stock, orders, shipments, DC
  inventory, promotions, price, assortment, item/store hierarchy, supply-chain, and
  forecast files or APIs. Every source is untrusted input.
- **Ingestion and validation:** reads immutable source extracts, rejects or quarantines
  invalid records, and records safe lineage metadata.
- **Canonical retail layer:** converts retailer-specific fields into Memento-owned,
  versioned concepts and contracts.
- **Deterministic metric engine:** reads canonical data and produces reproducible metrics.
- **Filesystem control plane:** immutable manifests and directory state identify source
  references, staging runs, quarantined failures, and published datasets for the MVP.
- **DuckDB + Parquet:** local analytical query and columnar storage boundary.

## Initial data flow

```text
Retailer/internal sources (untrusted)
          |
          v
Immutable local raw landing area
          |
          v
Validation + quarantine ----> safe validation summaries
          |
          v
Canonical retail Parquet
          |
          v
DuckDB deterministic metrics
          |
          v
Insights engine / product surface (future)

Filesystem manifests: source references, run outcomes, lineage pointers, and status
```

## Boundary rules

- Source payloads do not enter Git, logs, error messages, or model context.
- Raw inputs are read-only; canonical and derived outputs are replaceable artifacts.
- Validate before canonical data is published. Failed records are isolated from valid output.
- Use least-sensitive stable identifiers where possible; do not expose customer-specific
  identifiers outside their intended tenant or environment.
- Database credentials and filesystem roots enter through runtime configuration, not code.
- Local services bind to loopback by default. Production identity, tenant isolation,
  encryption, retention, backup, and deletion controls require design before real data.

## Current operational-state decision

The ingestion MVP does not use a persistent operational database. Its control state is
the ignored local filesystem: a source-reference manifest, unique staging directory,
safe quarantine summary, and immutable published manifest. DuckDB connections are
ephemeral and operate over Parquet. A Dockerized operational database may be introduced
only for a concrete approved need such as concurrent workers, resumable distributed
runs, or centralized configuration; it is not required merely to mirror this outline.

## Preconditions for customer data

Adding a `tenant_id` column alone does not establish isolation. Before confidential
customer data enters the system, approve authentication and authorization, tenant-scoped
storage or stronger physical isolation, encryption and key ownership, secrets handling,
retention and deletion, backup and recovery, payload-safe audit logging, production
access, monitoring, and incident response. Until then, this project is not approved for
confidential customer or production data.

## Open decisions

- Exact source location and Walmart extract contract.
- Cross-release catalog, supersession, and late-arriving correction policy.
- Production hosting, identity, tenancy, encryption, retention, and recovery model.
