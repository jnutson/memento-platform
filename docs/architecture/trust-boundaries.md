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
- **Docker database:** local operational metadata, configuration, and ingestion state.
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

Docker database: run metadata, configuration, lineage pointers, and status
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

## Open decisions

- Exact source location and Walmart extract contract.
- Canonical entity keys, schema versioning, and late-arriving correction policy.
- Production hosting, identity, tenancy, encryption, retention, and recovery model.
