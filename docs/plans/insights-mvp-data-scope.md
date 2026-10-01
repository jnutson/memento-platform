# Miro Toys OOS Prediction MVP — Data Scope

Status: accepted direction
Contract version: `miro-oos-data-scope-v1.6.0`

## Outcome

Provide the smallest trustworthy observable dataset needed for Memento to predict when
a scoped Miro Toys item at a Walmart store will go out of stock within 28 days and rank
eligible predictions by estimated lost retail sales, remaining reaction time, and
prediction confidence.

The product contract is `docs/product/mvp-product-shape.md`. Calculations are fixed in
`docs/product/mvp-metric-contract.md`. Terminology is governed by
`docs/product/memento-glossary.md` and the Walmart PSP Glossary it references.

## Fixed scope

- Company: `MIRO_TOYS` / Miro Toys.
- Retailer: synthetic Walmart US.
- Brand: source `BRAND_A`, displayed as Miro Spark through explicit mapping.
- Cohort: all 90 configured `BRAND_A` items across all 2,000 stores in the checked
  target reference snapshot.
- Coverage: published Walmart FY2027 through FY2028, with FY2026 retained only as
  internal comparable support and future facts revealed only through
  cutoff-safe immutable releases.
- Initial cutoff: `2027-01-30T12:00:00Z`; latest fully closed business date is January
  29, 2027 for every included store.
- Prediction horizon: 28 calendar days.
- Output: at most 10 ranked store-item OOS predictions per daily run.
- Ranking dimensions: impact, reaction time, and prediction confidence only.

No secondary insight or interactive scenario-planning capability is part of this MVP.

## Ownership boundary

```text
Synthetic Data repository owns:
  immutable observable Walmart releases
  + three focused Miro extensions
  + physically separate private evaluator truth

Memento platform owns:
  validation and canonicalization
  + interpretable demand forecast and WAPE band
  + deterministic low/base/high inventory projection
  + OOS prediction
  + estimated lost-sales calculation
  + impact, reaction, confidence, and rank scores
  + immutable ranked prediction output
  + offline evaluation of matured predictions
```

The generator creates observable conditions from which Memento can make the prediction.
It must not publish predicted OOS dates, lost-sales estimates, scores,
ranks, case labels, or expected conclusions.

## Walmart source schemas

Retain the existing six schemas:

- `calendar_dim`
- `store_dim`
- `omni_item_dimensions`
- `store_sales`
- `store_invt`
- `long_rng_store_dmd_frcst`

Do not mutate an accepted release. Generate a new Brand A/all-store world covering
published Walmart FY2027 through FY2028 and publish cutoff-safe immutable release sets with the
same six schemas and corrected replenishment values:

- On order is ordered store quantity not yet DC-invoiced.
- In transit is DC-invoiced store quantity not yet received and finalized.
- Receipts are sellable units received at the store on the business date.

The existing release whose on-order and in-transit values are identical remains
immutable historical evidence but is not the Miro OOS base release.

## Required synthetic extensions

Only three extension datasets are required.

### `dim_item`

Purpose: map Miro Toys/Miro Spark identity to the scoped Walmart items.

Primary key: `company_id x company_item_id`.

```text
company_id                       string; MIRO_TOYS
company_item_id                  string
company_item_name                string
display_brand_id                 string; MIRO_SPARK
op_cmpny_cd                      int8
wm_item_nbr                      int64
effective_from                   date32
effective_to                     date32, nullable
```

Rules:

- Each scoped Miro item resolves uniquely to one Walmart item in source `BRAND_A`.
- Source retailer brand and item attributes are never rewritten.
- IDs and mappings are deterministic and effective intervals do not overlap.
- Cost, case pack, dimensions, domestic/import distinctions, and margin fields are not
  required for this capability.

### `retailer_replenishment_commitment`

Purpose: expose deduplicated order-line state and expected store receipts known at each
release cutoff.

Primary key: `retailer_order_id x order_line_nbr x event_version`.

```text
retailer_order_id                string
order_line_nbr                   int32
event_version                    int32
store_nbr                        int32
op_cmpny_cd                      int8
wm_item_nbr                      int64
ordered_qty                      int32
invoiced_qty                     int32
received_qty                     int32
order_created_at                 timestamp[us, UTC]
approved_to_ship_at              timestamp[us, UTC], nullable
dc_invoiced_at                   timestamp[us, UTC], nullable
expected_store_receipt_date      date32, nullable
actual_store_receipt_at          timestamp[us, UTC], nullable
status_cd                        string
known_at                         timestamp[us, UTC]
```

Allowed statuses are `ordered`, `approved_to_ship`, `in_transit`,
`partially_received`, `received`, and `cancelled`.

Rules:

- Quantities are nonnegative, `invoiced_qty <= ordered_qty`, and
  `received_qty <= invoiced_qty`.
- Versions append monotonically and prior versions remain byte-identical.
- A release includes only versions with `known_at <= as_of`.
- Approval to ship is an observable precursor but does not create Walmart Store In
  Transit; DC invoice does.
- Expected dates revise only through a new version.
- Select one latest known version per PO line before aggregation.
- Open order, in transit, and daily receipts reconcile independently to `store_invt`
  under M-010.
- Publish every open PO plus completed/cancelled PO lines with activity in the trailing
  56 days. Historical reconciliation is limited to that declared retention window;
  observation-date M-010 reconciliation is mandatory.
- No DC topology, DC inventory, carrier, vendor, allocation, optimization, predicted
  outcome, or recommendation fields are required.

### `item_reaction_constraint`

Purpose: provide the minimum number of days Miro Toys needs to react before predicted
depletion.

Primary key: `company_id x item_scope_type_cd x item_scope_id x effective_from`.

```text
company_id                       string; MIRO_TOYS
item_scope_type_cd               string; all | brand | item
item_scope_id                    string
minimum_reaction_days            int32
effective_from                   date32
effective_to                     date32, nullable
```

Item overrides brand; brand overrides all. Every scoped item resolves exactly one
nonnegative active constraint. The dataset contains no score, rank, recommendation, or
simulated supply plan.

## Data-to-output path

| Stage | Observable inputs | Memento output |
|---|---|---|
| Validate | Manifests, six Walmart schemas, three extensions | accepted release set or failure |
| Forecast | POS, calendar, retailer forecast, inventory eligibility | base forecast, WAPE, low/base/high demand paths |
| Project | On hand plus deduplicated dated inbound | three deterministic 28-day inventory paths |
| Predict | Base-path depletion and unfulfilled demand | base OOS date, sensitivity dates, estimated lost units and sales |
| Rank | Prediction plus reaction constraint and data quality | impact, reaction, confidence, rank, top 10 |
| Evaluate offline | Later observable inventory, receipts, and POS | timing and precision metrics |

The low/base/high paths are fixed arithmetic transforms of the base forecast using
clamped historical WAPE. They are not probabilities, stochastic simulations, or
user-controlled scenarios.

## Private evaluator truth

Private truth may contain only:

- Actual latent daily demand for the configured cohort.
- Exact programmed inventory depletion and replenishment events.
- Exact stockout start and censored demand.
- Focal fixture identity and expected relative ranking behavior.

Private truth remains physically separate, uses blind canaries, and never enters an
observable manifest, product fixture, log, exception, model input, or user output.

## Required fixture cases

Create five unlabelled observable cases that isolate the focused behavior:

1. High estimated lost sales, adequate reaction time, and high confidence; ranks first.
2. Similar timing and confidence to case 1 but lower estimated lost sales; lower impact.
3. Similar impact and confidence but little or negative action slack; different reaction
   score.
4. Similar impact and reaction timing but sparse forecast history or degraded accepted
   inbound reconciliation; lower confidence.
5. Sufficient on-hand and inbound to avoid depletion on the deterministic base path;
   produces no OOS candidate.

At least one frozen prediction must mature into a later observable OOS within the full
28-day evaluation window. Observable rows must not contain fixture labels or Memento
answers.

## Release and validation gates

Fail publication on:

- Schema, type, key, nullability, enum, effective-date, or range violations.
- Missing configured item/store mappings or reaction constraints.
- Invalid PO-line quantities, lifecycle transitions, dates, or version order.
- Future knowledge or later revisions present before the release cutoff.
- Reconciliation above the accepted tolerance.
- Missing, changed, undeclared, symlinked, traversal, or hash-mismatched files.
- Any private truth, canary, prediction, loss estimate, score, rank, or
  fixture label in observable output.
- Nondeterministic replay from identical inputs.

The Walmart and extension packages remain undiscoverable until one deterministic
release-set manifest binds their exact manifest checksums and all controlling contract
versions. Only then may one atomic `current.json` update expose the source set. Source
or extension failure publishes no visible partial source set or downstream prediction
set. Content manifests exclude wall-clock timestamps and execution IDs; separate
execution metadata may retain them. Generated Parquet, manifests, releases, extensions,
and execution artifacts remain ignored.

## Explicitly deferred

- Interactive scenario planning and user-controlled what-if assumptions.
- Promotions, elasticity, assortment, trend, historical-OOS, margin, and space insights.
- Planogram data as a required MVP input.
- Store/DC assignment, DC inventory, and retailer network models.
- Recommended actions, order quantities, order mutation, allocation, or execution.
- Human feedback capture, online ranker learning, or generalized insight generation.
- Intraday prediction and unrestricted brands, items, stores, retailers, or companies.
- Miro factory, production, port, carrier, import, company-DC, or supply-plan datasets.

## Acceptance checks

- All 90 Miro Spark items and all 2,000 stores resolve deterministically to the checked
  source snapshots.
- The three extensions are immutable, cutoff-safe, independently validated, and
  sufficient to reproduce the focused fixture cases.
- Memento can compute every required prediction and ranking field from observable data
  alone.
- Ranking uses only estimated lost-sales impact, reaction score, and prediction
  confidence with declared weights and deterministic ties.
- A later release provides a complete 28-day outcome for at least one prior prediction.
- Identical inputs replay byte-identically, including both package manifests and the
  release-set manifest; a new release creates a new immutable evaluation without
  rewriting history.
- `current.json` points only to the validated release-set manifest, never to one package.
- Any invalid required input publishes nothing downstream.
- Logs contain metadata and counts, not rows; private truth remains inaccessible.
- No probability model, random sampling, Monte Carlo simulation, planogram, DC
  inventory, recommended action, secondary insight, feedback loop, or interactive
  scenario-planning input is required.
