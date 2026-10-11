# Synthetic Data Handoff — Memento Signal Full-Scale Acceptance

Status: ready for Synthetic Data verification and handback  
Prepared: 2026-10-09  
Source repository: `/Users/mininutson/Desktop/Synthetic Data`  
Consumer repository: `/Users/mininutson/Desktop/Memento_Analytics_Demo_1`  
Suggested task name: `verify-memento-signal-source-releases`

## Outcome

Verify and hand back the immutable synthetic source releases needed to run Memento
Signal's full 90-item, 2,000-store product acceptance. Do not rebuild the source world
unless the existing artifacts fail validation or no longer match the reviewed tracked
inputs.

The handback is complete when Memento receives validated paths and checksums for:

1. the initial prediction release at `2027-01-30T12:00:00Z`;
2. the matured evaluation release at `2027-02-27T12:00:00Z`; and
3. the complete FY2028 archive release at `2028-01-29T12:00:00Z`.

These releases must use the four-extension Memento Signal v1.0.0 contract, including
`company_item_economics`. The earlier three-extension `miro-oos-*` release identity is
historical and is not an acceptable handback.

## Repository boundary

Work only in `/Users/mininutson/Desktop/Synthetic Data`.

- Treat `/Users/mininutson/Desktop/Memento_Analytics_Demo_1` as read-only.
- Generated Parquet may be written only beneath Synthetic Data's configured, ignored
  `outputs/` and `releases/` roots. Never stage or commit generated data, and never copy
  it into the Memento consumer repository.
- Preserve the untracked `analysis/` directory and all unrelated planogram work.
- Do not modify, replace, or delete an immutable release in place.
- If a Memento consumer change appears necessary, report the exact incompatibility and
  stop; do not patch the consumer repository from this task.
- Use only synthetic inputs. Do not introduce customer data, credentials, or private
  truth into observable packages, logs, exceptions, fixtures, or model context.

The repository-specific `AGENTS.md` remains controlling for execution.

## Current state to verify, not assume

The following state was observed read-only on 2026-10-09:

- Branch: `codex/miro-brand-a-two-year`
- HEAD: `eaa1fb2` (`Add Memento Signal economics release contract`)
- Upstream: `origin/codex/miro-brand-a-two-year`
- Untracked unrelated path: `analysis/`
- Reviewed run profile: `config/runs/miro_brand_a_two_year.json`
- Reviewed economics artifact: `config/miro_signal/company_item_economics.json`
- Current local release pointer: release `9b132e3674c36aeb-20280129T120000Z`

Three Memento Signal v1.0.0 release-set manifests were present:

```text
releases/miro_brand_a_two_year/release-sets/9b132e3674c36aeb-20270130T120000Z/manifest.json
releases/miro_brand_a_two_year/release-sets/9b132e3674c36aeb-20270227T120000Z/manifest.json
releases/miro_brand_a_two_year/release-sets/9b132e3674c36aeb-20280129T120000Z/manifest.json
```

The initial release was observed with:

- 90 items and 2,000 stores;
- 65,520,000 `store_sales` rows through January 29, 2027;
- 65,520,000 `store_invt` rows through January 29, 2027;
- 10,080,000 retailer forecast rows;
- 4,156,084 retained replenishment event-version rows;
- 90 item mappings, three reaction-constraint rows, and 90 economics rows; and
- approximately 1.4 GiB of Walmart files plus 49 MiB of extensions.

Treat these observations as discovery evidence, not as passed acceptance checks. Recompute
and report them from the manifests and validators before handback.

The older `9f201b85...` releases use the superseded `miro-oos-v1.6.0` contract and omit
`company_item_economics`. Do not select them for Memento Signal acceptance and do not
delete them.

## Controlling contracts and precedence

This handoff was prepared from Memento branch `codex/harden-data-contract` at base
commit `890d68870f59c5642f37671686ca799cc4613596`. The contract snapshot includes
uncommitted documentation changes, so the commit alone is not its identity. At
preparation time the Memento working tree contained:

```text
 M README.md
 M docs/plans/brand-a-three-year-synthetic-run.md
 M docs/plans/insights-mvp-data-scope.md
?? docs/handoffs/synthetic-data-memento-signal-v1.md
?? docs/handoffs/synthetic-data-memento-signal-v1.sha256
```

The authoritative file-by-file SHA-256 snapshot, including this handoff, is recorded in
`docs/handoffs/synthetic-data-memento-signal-v1.sha256`. Verify every listed checksum
before implementation. A mismatch means the mutable path no longer identifies the
accepted snapshot; stop and request a refreshed handoff rather than silently using the
new file.

After verifying the fingerprints, read these before changing or validating the profile:

1. `/Users/mininutson/Desktop/Memento_Analytics_Demo_1/docs/product/mvp-product-shape.md`
   — product capability and acceptance behavior.
2. `/Users/mininutson/Desktop/Memento_Analytics_Demo_1/docs/product/mvp-metric-contract.md`
   — deterministic calculation inputs and knowledge-time requirements.
3. `/Users/mininutson/Desktop/Memento_Analytics_Demo_1/docs/plans/insights-mvp-data-scope.md`
   — dataset ownership and source contracts.
4. Brand A run plan — cohort, dates, scale, temporal projection, and publication
   requirements:
   `/Users/mininutson/Desktop/Memento_Analytics_Demo_1/docs/plans/brand-a-three-year-synthetic-run.md`
5. `/Users/mininutson/Desktop/Memento_Analytics_Demo_1/docs/product/memento-glossary.md`
   and `config/reference_sources/PSP Glossary.csv` — terminology.
6. `INSIGHTS_MVP_SYNTHETIC_DATA_BUILDER_HANDOFF.md` — historical implementation
   detail only where it does not conflict with the four-extension contracts above.

The active versions are:

```text
product     memento-signal-product-v1.0.0
metrics     memento-signal-metrics-v1.0.0
data scope  memento-signal-data-scope-v1.0.0
glossary    memento-glossary-v1.4.0
```

If two controlling sources conflict, stop and report the conflict rather than choosing
one silently.

## Fixed source contract

The release set binds one Walmart package containing six datasets and one Miro package
containing four physically separate extensions.

Walmart datasets:

1. `calendar_dim`
2. `store_dim`
3. `omni_item_dimensions`
4. `store_sales`
5. `store_invt`
6. `long_rng_store_dmd_frcst`

Miro extensions:

1. `dim_item`
2. `retailer_replenishment_commitment`
3. `item_reaction_constraint`
4. `company_item_economics`

The fixed cohort is all 90 configured `BRAND_A` items mapped to Miro Spark across all
2,000 stores in the checked target reference snapshot. Published observable coverage is
Walmart FY2027 through FY2028. FY2026 and later private facts may support generation and
evaluation but must not leak through a historical release cutoff.

Economics rows are effective-dated, nonnegative, USD synthetic unit costs. They are
source inputs for Memento's inventory-exposure calculation; Synthetic Data must not add
the annual carrying-cost rate. That rate is a separately approved, versioned Memento
configuration value.

The generator must not publish Memento-derived forecasts, low/base/high paths, predicted
OOS dates, signal eligibility, economic-impact results, scores, ranks, fixture labels,
recommendations, or expected conclusions.

## Required verification sequence

### 1. Establish tracked state

- Read `AGENTS.md`, `README.md`, the run profile, economics artifact, Miro generator,
  manifest schemas, and focused tests.
- Confirm the active branch and HEAD.
- Record tracked modifications and untracked paths before work.
- Confirm that every configured input hash used by the `9b132e...` releases still
  matches the current reviewed files.
- Do not clean, move, stage, or overwrite unrelated files.

### 2. Run narrow contract checks

From the Synthetic Data repository:

```bash
.venv/bin/pytest -q tests/unit/test_miro_oos.py
.venv/bin/python generate.py miro-oos-preflight
.venv/bin/python generate.py miro-oos-smoke
```

The smoke run must remain non-publishing. Confirm the four extension schemas, exact
economics coverage, deterministic identities, cutoff filtering, PO lifecycle behavior,
and atomic failure behavior.

### 3. Run the complete repository test suite

```bash
.venv/bin/pytest -q
```

Report the exact pass/fail/skip totals and duration. Do not weaken tests or validation
to accept an existing artifact.

### 4. Validate existing full-scale releases

For each `9b132e...` release-set manifest, independently verify:

- manifest safe-relative-path and checksum integrity;
- exact binding between release set, Walmart manifest, and extension manifest;
- exact contract versions and configuration hash;
- exact six-plus-four dataset inventory with no undeclared files;
- schemas, nullability, primary keys, enumerations, ranges, and references;
- 90-item and 2,000-store cohort identity and checked hashes;
- date bounds, row/file counts, and complete store-item-day density;
- cutoff safety for facts, forecasts, PO versions, and effective-dated extensions;
- correct 364-day comparable-calendar mappings and TY/LY reconciliation;
- PO event-version monotonicity, quantity inequalities, retention, and independent
  reconciliation of on-order, in-transit, and receipts;
- exactly one active USD economics row per scoped item at each cutoff;
- no private truth, canaries, Memento outputs, absolute paths, symlinks, execution IDs,
  wall-clock timestamps, or raw payloads in observable artifacts and manifests; and
- immutable replay behavior when the same content is published again.

Do not infer validity from the presence of `current.json`. If no standalone validator
covers a gate, add the smallest focused validation/test in Synthetic Data or report the
missing gate explicitly.

### 5. Regenerate only when necessary

Do not run a full materialization merely to prove that files exist. If existing releases
fail because they are stale or incomplete:

1. run preflight and record projected rows, files, disk, and runtime;
2. obtain any resource approval required by the local workflow;
3. generate one new content-addressed world from reviewed inputs;
4. publish all three cutoffs from that same world; and
5. preserve every prior immutable release.

Never patch generated Parquet rows, tune individual stores/items to manufacture a
desired result, or overwrite `9b132e...` in place. A reviewed source-parameter change
must create a new simulation and release identity.

## Handback to Memento

Return one concise machine-usable and human-readable delivery report containing:

```text
synthetic_data_git_commit
working_tree_status
simulation_id
configuration_hash
source_world_manifest_absolute_path
source_world_manifest_sha256
source_input_hashes
contract_versions
initial_release_set_manifest_absolute_path
initial_release_set_manifest_sha256
evaluation_release_set_manifest_absolute_path
evaluation_release_set_manifest_sha256
archive_release_set_manifest_absolute_path
archive_release_set_manifest_sha256
per_release_dataset_row_and_file_counts
per_release_date_bounds
validation_check_ids_and_results
test_commands_and_results
runtime_peak_memory_and_disk_use_when_measured
replay_evidence
unrun_checks_or_open_risks
```

The absolute manifest paths are local handoff coordinates, not manifest content. The
manifests themselves must retain safe relative paths and portable content identity.

Memento will then perform, in its own repository and ignored `data/` root:

```text
initial release -> ingest/canonicalize -> predict -> publish three signal types
evaluation release -> ingest/canonicalize -> evaluate frozen initial predictions
archive release -> ingestion/replay/archive acceptance
```

Memento owns candidate counts, mixed top-ten composition, ranking, precision at 10,
prediction-date error, API/UI checks, and final product acceptance. Synthetic Data may
assist by diagnosing source conditions, but it must not calculate or publish those
product outputs as source fields.

## Completion criteria

The Synthetic Data task is complete only when:

1. all three release checkpoints bind the same reviewed simulation and configuration;
2. each release contains exactly six Walmart datasets and four Miro extensions;
3. all source, temporal, reconciliation, privacy, determinism, and atomic-publication
   gates pass;
4. the initial release contains sufficient observable history and 28-day forward
   forecasts for Memento's cutoff-safe calculations;
5. the evaluation release contains a complete later observable 28-day outcome window;
6. the archive release closes FY2028 without mutating either earlier release;
7. existing target and planogram workflows remain unchanged;
8. generated artifacts remain ignored and no customer data or secrets are introduced;
9. the full test suite passes or every failure is reported without being hidden; and
10. the handback report provides exact manifests, checksums, counts, versions, resource
    evidence, replay evidence, and any unrun checks.

## Explicitly out of scope

- Changing Memento formulas, thresholds, weights, API, UI, or canonical schemas.
- Choosing Memento's annual carrying-cost rate.
- Adding probability claims, Monte Carlo prediction, interactive scenarios, or actions.
- Promotion elasticity, planogram analysis, DC topology, allocation, or recommendations.
- Production deployment, real customer data, authentication, tenancy, or retention.
- Deleting historical releases or unrelated work.

## Stop conditions

Stop and report rather than improvising if:

- a required Memento contract conflicts with the Synthetic Data implementation;
- a release references an unreviewed or missing input;
- validation would require changing an immutable artifact in place;
- full regeneration would exceed reviewed disk/runtime limits;
- private truth or customer-sensitive information appears in an observable boundary;
- a Memento consumer code change is required; or
- the existing release cannot be proven cutoff-safe and deterministic.
