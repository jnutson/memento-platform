# Brand A Two-Year Synthetic Data Run — Implementation Plan

Status: accepted implementation direction

Authority: this plan supersedes the cohort, date coverage, and release-publication
instructions in the earlier Synthetic Data builder handoff. The handoff remains
authoritative for unchanged schema, validation, truth-boundary, and safety requirements.

## Outcome

Create a new, independent Synthetic Data profile that uses the existing target engine
to generate the complete Miro Toys source world required by the focused OOS prediction
MVP:

- one retailer brand: source `BRAND_A`, displayed by Memento as Miro Spark;
- all 90 existing `BRAND_A` items;
- all 2,000 stores in the target reference snapshot;
- two complete published Walmart merchandising years;
- cutoff-safe retailer forecasts and explicit PO-line replenishment state;
- the three Miro extension datasets required by the MVP; and
- physically separate future/private truth for evaluation.

This is a new content-addressed run. It must not modify, reinterpret, or overwrite the
accepted `target` simulation or release.

## Date convention

“This year and next year” means complete Walmart merchandising years, not calendar
years. The preceding year is simulated only to populate comparable fields:

| Role | Walmart year | Date range |
|---|---:|---|
| This year | FY2027 | 2026-01-31 through 2027-01-29 |
| Next year | FY2028 | 2027-01-30 through 2028-01-28 |

The simulation also needs prior-year state and warmup. Use:

```text
prior_comparable_start_date = 2025-02-01
simulation_start_date       = 2024-12-07
observable_start_date       = 2026-01-31
world_end_date              = 2028-01-28
initial_prediction_as_of    = 2027-01-30T12:00:00Z
```

The full future world may be generated once, but facts after a release cutoff remain
private until a later immutable release makes them observable.

## Fixed scope and expected scale

The run uses the 90 items already assigned to `BRAND_A` by the target item generator
and every store in `config/reference_sources/target_reference.json`.

```text
store count                 2,000
item count                     90
store-item count           180,000
observable days                728
store_sales rows       131,040,000
store_invt rows        131,040,000
weekly target weeks             104
one forecast/target rows  18,720,000
```

These counts assume all 90 items are active, traited, and replenishable at all 2,000
stores for the core run. The engine must derive the counts from configuration and fail
if the materialized scope differs.

The generated scale is comparable to the existing one-year target release because the
new run has fewer store-item pairs. Preflight must still calculate disk, row, file, and
runtime estimates before materialization.

## Ownership boundary

The Synthetic Data repository owns:

- the seeded retail world and private future truth;
- Walmart-shaped observable inputs;
- explicit replenishment lifecycle events and snapshots;
- the Miro item map and reaction constraints;
- immutable, cutoff-safe releases and their manifests; and
- source-level validation and reconciliation.

Memento owns:

- WAPE, bias, weekday shares, and the base demand forecast;
- deterministic low/base/high demand and inventory paths;
- predicted OOS dates and sensitivity dates;
- estimated lost units and retail sales;
- impact, reaction, confidence, and rank scores; and
- the top-10 queue and offline evaluation.

Seeded randomness is allowed inside the synthetic world to create realistic variation.
It must replay identically from the same seed. The prohibition on Monte Carlo applies
to the Memento prediction model, not to generation of synthetic source observations.

## New run profile

Add a new profile rather than changing `config/runs/target.json`:

```text
config/runs/miro_brand_a_two_year.json
config/scenarios/miro_brand_a_oos.json
config/miro_oos/item_mapping.json
config/miro_oos/reaction_constraints.json
```

The run config must declare, rather than infer:

- `included_brands = ["BRAND_A"]`;
- the exact 90-item ID set or its checked content hash;
- the exact 2,000-store reference-snapshot hash;
- `assortment_rate = 1.0` for the included brand;
- every date boundary above;
- a fixed master seed;
- forecast lead and horizon rules;
- replenishment lifecycle timing rules;
- output and release roots unique to this profile; and
- all controlling Memento contract versions.

Suggested roots:

```text
outputs/miro_brand_a_two_year/
releases/miro_brand_a_two_year/
releases/miro_brand_a_two_year/extensions/<walmart-release-id>/
```

Generated outputs remain ignored. Configuration, schemas, tests, and documentation are
the only committed artifacts.

## Phase 1 — Parameterize the existing target engine

Refactor only hardcoded assumptions needed by this profile:

1. Accept an explicit run-config and scenario-config path in the target CLI.
2. Derive brands, item count, store count, assortment, dates, horizon length, comparable
   offsets, scenario counts, and validation totals from configuration.
3. Replace the FY2027-only `wm_week` logic with a configuration-backed internal Walmart
   calendar resolving every date from `simulation_start_date` through `world_end_date`,
   approximately FY2025 through FY2028. Only FY2027 through FY2028 are published;
   FY2026 remains internal support for FY2027 `ly_*` values and state continuity.
4. Replace fixed 364-day arrays and fixed `784`/`364` shape assertions with derived
   lengths.
5. Remove date literals from price events and lifecycle calculations; express any
   retained retail events relative to configured Walmart weeks.
6. Keep the existing `target` profile behavior and tests unchanged.

Do not build a second simulation engine. The new profile must reuse item generation,
seasonality, deterministic seed streams, partition writing, manifest hashing, staging,
and validation from the target engine.

## Phase 2 — Generate the Brand A retail world

Generate all store-item-days from one continuous stateful world so inventory and
replenishment do not reset at year boundaries.

Demand must retain the current engine's interpretable components:

```text
baseline velocity
* weekday factor
* calibrated monthly/holiday seasonality
* store factor
* item lifecycle factor
* deterministic seeded variation
```

Use global, reviewable parameters rather than hand-editing individual observable rows.
The world should create a useful distribution of forecast error, inventory coverage,
and OOS outcomes across Brand A without embedding Memento answers or fixture labels.

The existing broad `baseline / supply_failure / planning_failure / demand_shock`
allocation is not a product requirement. Replace it for this profile with the minimum
private causal variation necessary to produce:

- normal replenishment;
- a bounded set of delayed or short receipts;
- demand variation that produces different forecast WAPE values; and
- enough actual OOS outcomes to evaluate a ranked top 10.

Private causal labels remain outside observable files and manifests.

## Phase 3 — Replace the anonymous pipeline with PO-line lifecycle state

For this profile, a replenishment decision creates a stable PO line with a deterministic
identity. Its immutable versions expose only facts known at each version time.

Minimum lifecycle:

```text
ordered
-> approved_to_ship
-> DC invoiced / in_transit
-> partially_received or received
-> optional cancelled remainder
```

For the latest version known at a cutoff:

```text
open_order_units = max(ordered_qty - invoiced_qty, 0)
in_transit_units = max(invoiced_qty - received_qty, 0)
pipeline_units   = open_order_units + in_transit_units
                 = max(ordered_qty - received_qty, 0)
```

Requirements:

- no unit is counted in both open order and in transit;
- approval to ship does not become Walmart Store In Transit until DC invoice;
- receipts are positive received-quantity changes on their observable business date;
- partial invoices and receipts preserve the remaining quantity;
- late quantity remains open, in transit, overdue, or cancelled through a later
  version; it never disappears;
- expected receipt-date changes create a new version; and
- PO IDs and versions are deterministic and independent of processing order.

`store_invt.ty_on_order_qty`, `ty_in_transit_qty`, and `ty_rcpt_qty` must be derived from
the latest eligible PO-line state and independently reconcile to the PO-line extension.

## Phase 4 — Produce the required datasets

### Walmart observable datasets

Publish the same six source schemas, limited to Brand A and the full store set:

1. `calendar_dim`
2. `store_dim`
3. `omni_item_dimensions`
4. `store_sales`
5. `store_invt`
6. `long_rng_store_dmd_frcst`

`calendar_dim` covers both published merchandising years and may extend beyond a release
cutoff because it is reference data. POS, inventory, and receipts remain cutoff-bound.

For `store_sales` and `store_invt`, embedded `ly_*` fields must match the same
store-item on the Walmart comparable date 364 days earlier. The warmup/prior period is
used to populate FY2027 comparables but is not published as a third observable year.

### Retailer forecasts

Publish one frozen retailer forecast per store-item-target week, created four Walmart
weeks before the target week. This keeps the forecast table bounded while providing:

- at least eight completed historical forecast/actual pairs at every prediction cutoff;
- the full 28-day forward demand horizon;
- a visible mix of bias and WAPE across store-items; and
- no future actuals or truth-derived revisions.

Every forecast must be reproducible only from information available at its creation
week. The release projector includes it only when its creation week is known by the
release cutoff.

### Miro observable extension datasets

Publish a matched extension release containing exactly:

1. `dim_item` — maps all 90 Brand A items to Miro Toys/Miro Spark IDs.
2. `retailer_replenishment_commitment` — immutable PO-line versions known by the
   release cutoff.
3. `item_reaction_constraint` — one brand default plus only necessary item overrides.

The PO extension uses a bounded retention policy: include every open PO line at the
cutoff plus completed/cancelled lines with activity in the trailing 56 days. Historical
PO-to-snapshot reconciliation is required only for dates inside that declared window;
M-010 reconciliation at the observation date is always mandatory. The extension
manifest records the window and binds to the exact Walmart manifest checksum and every
controlling Memento contract version.

## Phase 5 — Add a real temporal release projector

The current target release builder copies an already-complete observable tree and only
checks maximum dates. That cannot safely publish rolling snapshots from a two-year
world. Change the new profile's publication path to project each release from the full
private world:

- `store_sales.bus_dt <= latest_fully_closed_business_date(store, as_of)`;
- `store_invt.bus_dt <= latest_fully_closed_business_date(store, as_of)`;
- PO versions require `known_at <= as_of`;
- forecasts require their creation week to be known by `as_of`;
- dimensions use the latest eligible effective records;
- calendar is bounded by the declared calendar horizon, not the fact cutoff; and
- private future truth is never copied into release staging.

The three required cutoffs occur at `12:00:00Z`, after every store in the contiguous-US
reference snapshot has closed the prior local business date. The projector derives and
records the latest fully closed date for each store timezone; it does not infer closure
from the UTC calendar date alone.

### Atomic release-set publication

Walmart and Miro packages are independently content-addressed but undiscoverable while
staged. Publication occurs only after both packages pass validation:

1. Write and validate the Walmart package and content manifest in staging.
2. Write and validate the matched Miro extension package and content manifest in
   staging. Its manifest contains the exact Walmart manifest SHA-256.
3. Write and validate one deterministic release-set manifest containing both package
   paths, both manifest checksums, the cutoff, configuration hash, and all controlling
   contract versions.
4. Atomically publish the release-set manifest.
5. Atomically update the profile's `current.json` to point to that release-set manifest.

Neither package is a supported discovery root on its own. If any validation or rename
fails, no release-set manifest or pointer becomes visible. `current.json` never points
directly to a Walmart package.

Content manifests and release-set manifests must be byte-identical for identical
inputs. Exclude wall-clock timestamps, execution UUIDs, host paths, and other run-specific
values from content identity and content manifests. Record those only in separate,
non-authoritative execution metadata.

Materialize these minimum release checkpoints:

| Release | Purpose | Latest actual business date |
|---|---|---|
| `2027-01-30T12:00:00Z` | Initial MVP prediction | 2027-01-29 |
| `2027-02-27T12:00:00Z` | Complete 28-day evaluation | 2027-02-26 |
| `2028-01-29T12:00:00Z` | Complete FY2028 archive | 2028-01-28 |

The generator should support additional cutoffs without regenerating or changing the
underlying world.

## Phase 6 — Source and release validation

Add validation for:

- exact brand, item, store, date, and row-count scope;
- complete store-item-day density for both daily fact tables;
- two-year published Walmart calendar boundaries and 364-day comparable mappings;
- exact TY/LY reconciliation;
- forecast creation strictly before target week and before release visibility;
- at least eight completed forecast/actual pairs per store-item at the initial cutoff;
- four forward target weeks available at the initial cutoff;
- PO identity, version monotonicity, quantity inequalities, and lifecycle transitions;
- independent on-order, in-transit, and receipt reconciliation;
- cutoff safety for every release;
- absence of Memento predictions, bands, losses, scores, ranks, labels, and canaries;
- exact manifest inventory, safe relative paths, hashes, and no symlinks;
- exact Walmart-manifest binding and controlling versions in each extension manifest;
- atomic release-set discovery with `current.json` pointing only to its manifest;
- absence of wall-clock timestamps and execution IDs from deterministic content
  manifests;
- deterministic replay from the same seed and inputs; and
- atomic failure behavior for source, extension, and release validation errors.

Logs contain only IDs, versions, counts, durations, resource estimates, and reason
codes. They must not contain source rows, PO payloads, private truth, or canaries.

## Phase 7 — Cross-repository MVP fitness check

After source validation, run the Memento calculation contract against the initial
release without using private truth. This is an integration acceptance check, not a
Synthetic Data calculation stage.

Require:

- at least 10 eligible Brand A store-item base-path OOS predictions so ranking and
  truncation are exercised;
- variation in estimated impact, reaction score, and interpretable confidence;
- predictions trace only to observable source releases;
- deterministic ordering and byte-identical replay; and
- no generator-provided OOS date, loss, confidence, or rank.

After the evaluation release, use only later observable POS/inventory to calculate
precision at 10 and lead-time error for frozen predictions. Private truth may separately
audit censored demand and exact lost units but cannot change product output.

If the global generator parameters do not produce adequate candidate coverage, adjust
reviewed demand/replenishment parameters and create a new simulation identity. Never
patch observable rows or select stores/items because they produce favorable answers.

## Tests and execution order

1. Unit-test configuration parsing and all derived date/count calculations.
2. Unit-test internal FY2024–FY2028 calendar boundaries and published comparable dates.
3. Unit-test Brand A/all-store cohort construction and row-order independence.
4. Unit-test PO-line transitions, partial quantities, deduplication, and reconciliation.
5. Unit-test cutoff projection independently for each dataset.
6. Run a minimized two-store/two-item/two-year fixture through both release cutoffs.
7. Run the existing complete Synthetic Data test suite to prove target compatibility.
8. Run the new profile preflight and one-store-shard smoke without publication.
9. Review estimated disk and runtime before authorizing the full materialization.
10. Generate the full world once and validate it.
11. Materialize and independently validate the three immutable releases and matched
    extensions.
12. Run the cross-repository Memento fitness check and record results without copying
    generated data into Git.

## Expected implementation areas

```text
config/runs/miro_brand_a_two_year.json
config/scenarios/miro_brand_a_oos.json
config/miro_oos/
src/synthetic_retail/target.py
src/synthetic_retail/world.py or a focused calendar helper
src/synthetic_retail/contracts.py
src/synthetic_retail/release.py
src/synthetic_retail/miro_oos.py
src/synthetic_retail/cli.py
schemas/manifests/
tests/unit/
tests/contracts/
tests/integration/
README.md
INSIGHTS_MVP_SYNTHETIC_DATA_BUILDER_HANDOFF.md
```

Avoid empty abstraction layers. A focused helper is warranted only where calendar,
PO lifecycle, or release projection logic has a narrow independently testable contract.

## Controlling contract versions

The four Memento contracts are versioned together for this accepted direction and
define Miro Toys as all 90 `BRAND_A` items across the 2,000-store target snapshot:

- `docs/product/mvp-product-shape.md` — `miro-oos-product-v1.6.0`
- `docs/product/mvp-metric-contract.md` — `miro-oos-metrics-v1.6.0`
- `docs/plans/insights-mvp-data-scope.md` — `miro-oos-data-scope-v1.6.0`
- `docs/product/memento-glossary.md` — `memento-glossary-v1.3.0`
- `INSIGHTS_MVP_SYNTHETIC_DATA_BUILDER_HANDOFF.md`

The equations and single OOS-prediction capability do not change. Only the configured
cohort, date coverage, release semantics, and data-builder instructions change. This
plan and those contract versions control implementation.

## Acceptance criteria

1. A new simulation identity covers exactly Brand A's 90 items, all 2,000 configured
   stores, and published FY2027–FY2028 without changing any accepted prior release.
2. The two daily fact datasets each contain exactly 131,040,000 unique store-item-day
   rows in the complete FY2028 release.
3. Calendar, Walmart weeks, and TY/LY comparable values are correct across both published
   years and year boundaries.
4. The initial `2027-01-30T12:00:00Z` release exposes actuals only through the latest
   fully closed store-local date, January 29, 2027, and includes the reference calendar
   and known forecasts needed for a 28-day prediction.
5. On-order, in-transit, and receipts are derived from explicit, versioned PO lines,
   are disjoint where required, and reconcile independently.
6. All 90 Miro mappings and all reaction constraints resolve deterministically.
7. The initial source set enables at least 10 independently computed OOS candidates
   with variation across impact, reaction, and confidence.
8. The evaluation release contains a complete observable 28-day outcome window for the
   frozen initial predictions without future leakage.
9. The archive release contains both requested years; identical inputs replay to
   identical files, content manifests, release-set manifest, and release ordering.
10. The Walmart and extension packages become discoverable only through one atomically
    published release-set manifest; any failure publishes no visible partial source set.
11. Source, extension, or calculation failure publishes nothing; logs contain no rows;
    private truth and generated data remain untracked and ignored.
12. No Monte Carlo prediction, probability estimate, scenario-planning UI input,
    recommended action, or secondary insight is added to the Memento MVP.
13. The delivery report states exact runtime, disk use, row/file counts, release IDs,
    validation results, full-run status, and any skipped check without inference.

## Explicitly out of scope

- Other brands, departments, retailers, or store universes.
- Interactive scenario planning and user-authored what-if assumptions.
- Memento-side Monte Carlo simulation or probability estimation.
- Promotion response, elasticity, shelf-space, trend, or generalized insights.
- DC inventory, store/DC topology, vendor, carrier, factory, port, or global supply
  planning.
- Purchase recommendations, PO mutation, allocation, or autonomous execution.
- Retrofitting or deleting the existing target release.

## Accepted decisions

“All stores” means the 2,000-store target reference snapshot. The year convention is
Walmart FY2027–FY2028. FY2026 is internal support for comparable fields, not a published
fact year. These decisions fix the row counts and contract scope above.
