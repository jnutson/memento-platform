# Walmart Observable Release to Memento Dataset MVP

Status: builder-ready
Task: `build-walmart-ingestion-mvp`

## Outcome

Build the smallest credible local pipeline that accepts an explicit Walmart-shaped
observable release manifest and publishes one immutable, validated Memento dataset for
downstream DuckDB analytics.

The first supported source is the synthetic release manifest at:

```text
/Users/mininutson/Desktop/Synthetic Data/releases/target/
437b6da3ad31abe0-20270130T000000Z/observable/manifest.json
```

The completed product loop is:

```text
explicit release manifest
  -> immutable raw reference
  -> source validation
  -> Walmart adapter
  -> canonical Parquet candidate
  -> canonical validation
  -> atomic Memento dataset release
```

Ingestion owns source identity, provenance, replay, run state, and safe handoff.
Validation observes and reports. Canonicalization performs explicit Walmart-to-Memento
mapping. Analytics consumes only a published Memento manifest.

## Non-goals

- Metrics, insights, dashboards, or forecasting.
- Real customer or production data.
- Network acquisition, SFTP, APIs, object storage, or streaming.
- A generic mapping DSL or runtime plugin framework.
- A second retailer adapter or speculative cross-retailer abstractions.
- Cross-release merging, corrections, or slowly changing dimensions.
- Partial publication after a blocking validation failure.
- Silent repair, clamping, deduplication, or coercion of invalid values.
- A new analytics engine or persistent datastore.
- Committing the full source release or generated Parquet.

## Source contract

The adapter accepts only an explicit standalone observable release manifest. It must
independently validate the external contract and must not depend at runtime on the
synthetic generator package.

| Walmart source | Rows in target release | Memento canonical output |
|---|---:|---|
| `calendar_dim` | 364 | `calendar_day` |
| `store_dim` | 2,000 | `location` |
| `omni_item_dimensions` | 400 | `product` |
| `store_sales` | 174,720,000 | `sales_daily` |
| `store_invt` | 174,720,000 | `inventory_daily` |
| `long_rng_store_dmd_frcst` | 24,960,000 | `demand_forecast_weekly` |

The release contains 6,243 Parquet files and about 1.5 GB. Fact transformations and
validations must use set-based DuckDB scans or Parquet metadata. Python must not
materialize complete fact tables or iterate over individual fact rows.

## Architecture and boundaries

### Orchestrator

The orchestrator owns:

- Explicit manifest-path intake and safe path resolution.
- Run identity and lifecycle.
- Adapter selection from a small explicit registry.
- Staging and quarantine locations.
- Phase ordering, failure state, idempotency, and atomic publication.

It must not contain Walmart field mappings or retailer-specific rules.

Suggested run states:

```text
REGISTERED
SOURCE_VALIDATING
SOURCE_VALID
CANONICALIZING
CANONICAL_VALIDATING
PUBLISHED
FAILED
```

### Adapter

Define a narrow interface with behavior equivalent to:

```python
class SourceAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def inspect(self, manifest_path: Path) -> SourceInventory: ...
    def validate_source(self, inventory: SourceInventory) -> ValidationReport: ...
    def canonicalize(
        self,
        inventory: SourceInventory,
        candidate_root: Path,
        run_context: RunContext,
    ) -> CanonicalCandidate: ...
```

Implement only `WalmartObservableReleaseV1Adapter`. The adapter owns the accepted
manifest and physical schema versions, required source datasets, enumerations,
calendar semantics, mappings, and source-specific rules.

### Validation

Validation produces `PASS`, `WARN`, or `FAIL` results containing only safe metadata:

- Rule ID and severity.
- Dataset and optional file or partition identifier.
- Count and safe summary.

It must not emit raw rows, source values, credentials, or connection strings. A `FAIL`
at either validation gate prevents publication. Warnings are retained in the released
manifest.

### Local storage

Keep all data-bearing artifacts under ignored `data/` paths:

```text
data/
  raw/<source-id>/source-reference.json
  staging/<run-id>/canonical/
  staging/<run-id>/validation/
  quarantine/<run-id>/validation-summary.json
  canonical/<memento-dataset-id>/manifest.json
  canonical/<memento-dataset-id>/<canonical-table>/
  metadata/ingestion.db
```

For this immutable local release, raw landing may be a sealed reference rather than a
second 1.5 GB copy. It records the absolute manifest path, manifest hash, release ID,
file-inventory identity, classification, and receipt time. It never mutates the source.

Use a small local ignored metadata database only if needed to prove restart and replay
behavior. Do not add Postgres or a Docker service without approval.

### Publication

Write only beneath `data/staging/<run-id>` until canonical validation passes. Then:

1. Inventory and hash the canonical output.
2. Write the Memento manifest last.
3. Derive a deterministic dataset ID from the source fingerprint, adapter version,
   canonical contract version, transformation version, and validation contract version.
4. Return the existing release when the same dataset ID is already published.
5. Atomically rename the candidate to `data/canonical/<dataset-id>`.
6. Mark the run published only after the rename succeeds.

Never overwrite a published dataset.

## Memento canonical V1

The exact V1 column names, order, DuckDB types, nullability, keys, enumerations,
identifier encoding, monetary conversion rules, lineage placement, and compatibility
policy are fixed by [Canonical Retail Contract V1](../architecture/canonical-retail-v1.md).
The builder must implement that contract without inventing alternative schema semantics.

Preserve the lowest useful source grain.

### `calendar_day`

Grain: `calendar_date x retail_calendar_id`.

Required concepts include calendar date/year/quarter/month, retail year/quarter/month/
week, retail year-week, comparable date, and comparable retail year-week. Use an
explicit calendar identity such as `walmart-454`; Walmart week numbering is not a
universal calendar.

### `location`

Primary key: deterministic `location_id`.

Include namespaced source identifiers, country, name, type, status, city, county,
state/province, postal code, coordinates, region, market, and timezone.

### `product`

Primary key: deterministic `product_id`.

Include namespaced source identifiers, product name and description, UPC, brand,
department/category/subcategory/fineline codes and names, status, effective date,
replenishment flag, unit of measure, base unit retail amount, and currency.

### `sales_daily`

Grain:

```text
business_date x location_id x product_id x channel x retail_type
```

Measures include sales quantity and amount plus explicitly named source-provided
comparison quantity and amount. Do not represent the supplied LY measures as
independently ingested historical facts.

### `inventory_daily`

Grain: `business_date x location_id x product_id`.

Preserve current and source-provided comparison values for on-hand, on-order,
in-transit, receipts, shelf capacity, assortment, replenishment, retail amount, unit
retail, and currency.

### `demand_forecast_weekly`

Grain:

```text
forecast_created_retail_year_week
x target_retail_year_week
x location_id
x product_id
```

Measure: forecast quantity.

### Identifier policy

Identifiers must be deterministic, namespaced, and independent of run order, time, or
filesystem location. Conceptually:

```text
location_id = stable_id("walmart", source_company_id, source_location_id)
product_id  = stable_id("walmart", source_company_id, source_product_id)
```

The exact SHA-256 preimage and prefixed encoding are defined in the canonical contract.
Implement its test vectors and retain the full digest.

## Source validation gate

Before canonicalization, fail closed on:

- Missing, non-regular, implicit, or unsafe manifest paths.
- Invalid JSON or unsupported manifest schema version.
- A dataset type other than `observable`.
- Invalid release identity or required metadata.
- Any false release gate.
- Duplicate dataset names or file paths.
- Absolute, traversing, escaping, symlinked, or special-file inputs.
- Missing or unexpected required datasets.
- Private/truth datasets or forbidden columns.
- A physical file inventory that differs from the manifest.
- Byte-size, file-hash, or dataset-tree-hash mismatch.
- Unsupported schema versions or physical schema drift.
- Inconsistent schemas within a dataset.
- Partition paths that contradict declared partition columns.
- Row counts or date bounds that do not reconcile.
- Missing primary-key columns, null required values, or duplicate keys.
- Broken dimension references.
- Invalid fact dates or forecast ordering.
- Forecast target weeks absent from the calendar.
- Non-finite numeric values.

Producer claims such as `duplicate_check: passed` are evidence, not a substitute for
consumer verification.

The target release has a future `as_of` relative to the current project date. It may
pass only when the run is explicitly classified as synthetic. Non-synthetic runs must
reject future `as_of` values beyond a small configured clock-skew allowance.

## Canonicalization rules

- Rename Walmart fields into Memento terminology.
- Cast only through declared, lossless conversions.
- Pin the `rpt_cd` mapping in the adapter.
- Pin or preserve `svc_chnl_nm` as a namespaced enumeration.
- Map Walmart calendar fields through `walmart-454` semantics.
- Generate deterministic product and location IDs.
- Set `source_system = "walmart"` where relevant.
- Remove physical layout fields such as `store_shard` from canonical contracts.
- Preserve source grain and negative values unless an explicit semantic rule applies.
- Never silently fill, clamp, deduplicate, discard, or repair records.

For this release-contract adapter, rejected rows cause the dataset to be withheld.

## Canonical validation gate

Require:

- Exact versioned canonical schemas and nullability.
- Exact column order, physical types, closed enumerations, and monetary precision from
  the canonical V1 contract.
- Canonical primary-key uniqueness.
- Deterministic identifier stability.
- Every fact location, product, date, and retail week resolves to its dimension.
- Source and canonical row counts reconcile for each mapping.
- Finite monetary and quantity values with documented range checks.
- Forecast creation week does not follow its target week.
- No source-only physical field escapes the adapter.
- Walmart identifiers are not unnamespaced canonical primary keys.
- Manifest file inventory, hashes, counts, and date bounds match physical output.
- Only atomically published directories are discoverable by analytics.

Inventory-flow or weekly/daily reconciliation may be a warning unless every required
term and grain is present in the source contract.

## Expected repository changes

The builder may simplify names but should stay within these boundaries and avoid empty
framework modules:

```text
pyproject.toml
README.md or focused local-run documentation
docs/architecture/ingestion.md
docs/architecture/canonical-retail-v1.md
docs/architecture/trust-boundaries.md
src/memento/cli.py
src/memento/ingestion/{models,manifest,storage,orchestrator}.py
src/memento/adapters/{base,walmart_observable_v1,walmart_schemas}.py
src/memento/validation/{models,source,canonical}.py
src/memento/canonical/{schemas,ids,writer}.py
tests/fixtures/walmart_observable_v1/
tests/unit/
tests/integration/
```

Prefer DuckDB and Pytest. Add JSON Schema validation only if useful. Add PyArrow only
if DuckDB cannot provide the exact Parquet schema/nullability inspection required.

## Fixtures, classification, and lineage

The supplied release is synthetic, external, and immutable. Do not copy it into the
repository. Commit only minimized reviewed synthetic fixtures covering all six source
datasets and key failure modes.

Fixtures should cover path traversal, missing and undeclared files, hash mismatch,
schema drift, duplicate keys, missing references, unsupported enumerations, future
`as_of` without synthetic classification, canonical failure, and identical replay.

Every published dataset must identify:

- Source manifest location, hash, release ID, and declared `as_of`.
- Source classification.
- Adapter ID and version.
- Canonical contract and transformation versions.
- Validation rules and PASS/WARN results.
- Canonical files, hashes, row counts, and date bounds.

Dataset- and file-level lineage is sufficient for V1 because mappings preserve grain.

## Acceptance checks

1. A valid minimized six-table release produces exactly one published Memento dataset
   whose six canonical tables are queryable with DuckDB.
2. Replaying the identical source and versions returns the same dataset ID without
   rewriting or duplicating data.
3. Missing, changed, undeclared, hash-mismatched, or schema-drifted source files fail
   before canonicalization and publish nothing.
4. Unresolved canonical product, location, date, or week references fail canonical
   validation and remain undiscoverable to analytics.
5. A failure after staging begins cannot create a partial published dataset, and a later
   clean run needs no destructive manual recovery.
6. Logs and errors contain rule IDs, counts, and safe identifiers but no complete rows,
   sensitive values, credentials, or connection strings.
7. Source and generated data remain ignored, and the external release remains unchanged.
8. The canonical output preserves the source grain and reconciles row counts.
9. An opt-in full-release smoke check validates and transforms the supplied 1.5 GB
   synthetic release with bounded memory. If it is not run, the builder reports it as
   unrun rather than inferring success from the manifest.

## Narrowest useful verification

Run, in order:

1. Unit tests for path safety, deterministic IDs, mappings, and validation severity.
2. One integration test over a minimized valid six-table release.
3. Focused failure tests for both publication gates and atomicity.
4. Idempotent replay test.
5. Repository diff and ignored-artifact inspection.
6. Optional full synthetic release smoke test after fixture tests pass.

## Decisions requiring approval

Stop before:

- Processing any source not confirmed synthetic.
- Copying, moving, deleting, or modifying the supplied external release.
- Adding Postgres, another datastore, or persistent Docker services.
- Changing canonical grain or publishing partial data after blocking failures.
- Adding another retailer, generic mapping language, or production interfaces.
- Defining production tenancy, identity, encryption, retention, backup, or deletion.
- Deploying or exposing the pipeline externally.
- Weakening validation to make the release pass.
- Accepting a future-dated release without explicit synthetic classification.
- Choosing a merge or correction policy across source releases.

## Builder handoff

- **Task name:** `build-walmart-ingestion-mvp`
- **Outcome:** Implement a local manifest-driven Walmart observable-release adapter
  that independently validates the six source datasets and atomically publishes one
  immutable Memento canonical dataset for DuckDB analytics.
- **Acceptance checks:** A minimized valid release publishes six queryable canonical
  datasets; replay is idempotent; source and canonical failures publish nothing;
  output is deterministic and lineage-complete; logs contain no rows; generated data
  remains ignored; the optional full-release smoke result is reported accurately.
- **Review intent:** Independently verify trust boundaries, immutable source handling,
  path safety, deterministic mappings, grain preservation, validation separation,
  atomicity, lineage, safe fixtures, and the absence of sensitive or untracked data.
