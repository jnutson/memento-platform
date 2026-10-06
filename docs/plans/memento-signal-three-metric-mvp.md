# Memento Signal Three-Metric MVP — Builder Plan

Status: proposed builder handoff

## Outcome

Rename the product surface to **Memento Signal** and deliver one deterministic ranked
queue containing three signal types:

1. **Availability Risk** — the existing 28-day predicted OOS and lost-sales capability.
2. **Demand Momentum Gap** — a persistent, stockout-aware divergence between recent
   demand and the retailer forecast, expressed as forward unit, retail-sales, and
   contribution impact.
3. **Inventory Imbalance Exposure** — projected inventory above a deterministic policy
   band after eligible inbound and demand, expressed as excess units, inventory cost,
   and 28-day carrying-cost exposure.

The product must demonstrate that heterogeneous signals can be compared without hiding
their different economic meanings. Each candidate retains its native metric values and
economic basis. A common score ranks candidates using type-relative impact, reaction
time, and confidence. The default UI shows the immutable overall top ten and permits
signal-type filtering without recomputing or renumbering ranks.

This is the smallest working loop:

```text
validated retailer + approved brand inputs
    -> canonical data with lineage
    -> three deterministic metric pipelines
    -> immutable unified signal set
    -> read-only API
    -> one Memento Signal queue and evidence view
```

## Non-goals

- No recommendations, order quantities, transfers, PO mutation, or execution controls.
- No probability claims, machine-learned ranking, Monte Carlo simulation, or editable
  scenario inputs.
- No promotion, distribution white-space, elasticity, planogram, margin-optimization,
  or retailer-deduction feature in this milestone.
- No new database, event bus, generalized metric framework, or production deployment.
- No customer data, authentication, tenancy, or access-control work.
- Do not modify `/Users/mininutson/Desktop/Synthetic Data`. The full-run source change
  identified below requires a separately authorized task in that repository.

## Fixed product semantics

### Common grain and horizon

The persisted unit is:

```text
signal_as_of x store_id x product_id x signal_type x signal_episode
```

Use the same immutable cutoff, store-local observation date, 28-day horizon, Miro Toys
and Miro Spark cohort, and source-release binding as the current OOS contract. Persist
every eligible candidate, assign ranks before truncation, and display at most ten.

Every signal publishes:

```text
signal_id
signal_type                         availability | demand_momentum | inventory_imbalance
signal_direction                    risk | acceleration | deceleration | excess
signal_as_of
store_id
product_id
headline_metric_name
headline_metric_value
estimated_retail_sales_impact_amount
estimated_contribution_impact_amount
estimated_cost_impact_amount
economic_impact_basis
days_until_material_impact
minimum_reaction_days
action_slack_days
impact_score
reaction_score
confidence_score
rank_score
overall_rank_position
signal_type_rank_position
is_overall_top_10
source and calculation lineage
```

Nullable economic fields must remain null when they do not apply; do not convert a
missing value to zero. UI labels must distinguish revenue opportunity, contribution
impact, inventory capital, and carrying cost.

### Shared ranking

Do not compare raw lost sales, contribution opportunity, and carrying cost as if they
were the same measure. Compute `impact_score` by applying the existing deterministic
midrank normalization independently within each `signal_type` using that type's
contracted primary economic value:

- Availability Risk: estimated lost retail sales.
- Demand Momentum Gap: absolute estimated contribution impact.
- Inventory Imbalance Exposure: inventory cost exposed plus 28-day carrying cost.

Then reuse the current weights:

```text
rank_score = 0.50 * impact_score
           + 0.30 * reaction_score
           + 0.20 * confidence_score
```

Sort by rank score, primary economic value, days until material impact, signal type,
store ID, product ID, and signal ID. Define and pin the exact signal-type lexical order
in the metric contract. There are no type quotas or UI-side sorting rules; fixtures must
naturally place all three types in the visible queue.

### Availability Risk

Retain the implemented OOS formulas, low/base/high paths, candidate eligibility,
evidence, and reason codes as the authoritative calculation. Adapt its published row to
the common signal schema without changing its predicted date or lost-sales result.

When an approved effective unit cost is available, additionally publish contribution
margin at risk:

```text
estimated_contribution_impact_amount
  = estimated_lost_units * max(realized_unit_price - unit_cost_amount, 0)
```

The primary ranking value remains lost retail sales for continuity with the accepted
Availability contract.

### Demand Momentum Gap

Use eight completed Walmart weeks ending before `observation_date`. Reuse the current
knowledge-time-safe retailer forecast selection and exclude negative-sales and observed
OOS-censored days. For each store-item:

1. Calculate eligible actual units and the eligible retailer forecast for each week.
2. Use the prior six weeks to establish the historical actual-to-forecast baseline.
3. Use the most recent two weeks to establish the recent actual-to-forecast ratio.
4. Require both recent weeks to have the same direction relative to baseline; otherwise
   emit `demand_momentum_not_persistent` and publish no candidate.
5. Apply the recent-to-baseline ratio to the already selected four forward retailer
   forecasts. Clamp the multiplier to a versioned reviewed range, initially `[0.50, 1.50]`.
6. Subtract the unadjusted forward retailer forecast to obtain the 28-day gap.
7. Require the absolute gap to exceed the forecast-error band derived from historical
   WAPE. This is the materiality gate; do not add a dollar threshold.

Publish acceleration and deceleration separately:

```text
forecast_gap_units
estimated_retail_sales_impact_amount = abs(forecast_gap_units) * realized_unit_price
estimated_contribution_impact_amount = abs(forecast_gap_units)
                                         * max(realized_unit_price - unit_cost_amount, 0)
```

For acceleration, the amounts describe forward opportunity at risk if the retailer
forecast remains unchanged. For deceleration, they describe forecast overstatement and
potential contribution exposure; they are not guaranteed savings.

`days_until_material_impact` is the first horizon date on which cumulative absolute gap
units reach 50% of the 28-day gap. Confidence combines forecast quality, data
completeness, and directional persistence using the existing `0.50 / 0.30 / 0.20`
weights. Evidence contains the eight historical weekly pairs and the 28 forward daily
retailer/base/momentum-adjusted values.

### Inventory Imbalance Exposure

Reuse the same base demand vintage, deduplicated scheduled inbound, and deterministic
inventory projection as Availability Risk. This signal is intentionally an excess-risk
signal for the MVP; shortage and depletion remain Availability Risk so the unified queue
does not duplicate the same episode.

Derive the policy band from existing reaction time and forecast uncertainty:

```text
safety_days = ceil(7 * clamped_wape)
target_cover_days = minimum_reaction_days + safety_days
target_units = mean_base_daily_demand * target_cover_days
projected_excess_units = max(projected_base_ending_units_day_28 - target_units, 0)
inventory_cost_exposed = projected_excess_units * unit_cost_amount
carrying_cost_28d = inventory_cost_exposed * annual_carrying_cost_rate * 28 / 365
```

The carrying rate is a versioned product configuration value, not a user-editable UI
assumption. A candidate requires positive projected excess units under the base path and
no base-path OOS within the horizon. `days_until_material_impact` is the first day the
base projection exceeds the date-specific target band and remains above it through day
28. Low/base/high paths provide timing stability; confidence uses forecast quality,
data completeness, and path stability with the common weights.

The signal reports inventory capital and carrying-cost exposure. It must not call those
amounts realized loss, guaranteed savings, markdown loss, or transferable inventory.

## Required data-contract change

The current observable inputs do not contain an approved brand unit cost. Add one
effective-dated internal input at the existing release-set boundary:

```text
company_item_economics
  company_id
  company_item_id
  currency_code                  USD for MVP
  unit_cost_amount               DECIMAL(20,2), nonnegative
  effective_from
  effective_to                   nullable
```

Requirements:

- Exactly one effective row resolves for every scoped item at the cutoff.
- It is a Miro/internal input, not inferred from Walmart retail values.
- Its package manifest, checksum, classification, and effective version flow into the
  canonical and signal manifests.
- Tests use minimized synthetic values only.
- Missing, overlapping, negative, non-USD, or unmapped values fail publication.

Version the product, metric, data-scope, canonical, signal-publication, and API contracts
together. Keep old immutable OOS artifacts readable; do not rewrite an existing release.
The builder may implement the consumer contract and fixtures in this repository, but
must stop short of claiming full-scale acceptance until the source repository publishes
the new input through an authorized change.

## Implementation boundaries and expected files

### Product and architecture contracts

Update or add:

- `README.md`
- `docs/product/mvp-product-shape.md`
- `docs/product/mvp-metric-contract.md`
- `docs/product/memento-glossary.md`
- `docs/plans/insights-mvp-data-scope.md`
- `docs/architecture/canonical-retail-v1.md`
- `docs/architecture/oos-prediction-serving.md` or a narrowly renamed signal-serving
  replacement

Document Memento Signal, the three calculations, exact thresholds, reason codes,
numeric behavior, unified ranking, immutable publication, and safe display language.

### Canonical ingestion

Expected implementation areas:

- `src/memento/miro.py`
- `src/memento/orchestrator.py`
- `src/memento/release_set.py`
- `tests/test_release_set_ingestion.py`
- new focused ingestion tests for `company_item_economics`

Add exact schema, effective-date, mapping, currency, and range validation. Publish a
physically distinct canonical `company_item_economics` dataset; never join cost into raw
retailer facts or log its row values.

### Calculation and publication

Preserve `src/memento/metrics.py` for small pure equations. Prefer two narrow modules
for the new calculations and one explicit orchestrator/publication module rather than a
plugin framework:

- `src/memento/demand_signal.py`
- `src/memento/inventory_signal.py`
- `src/memento/signals.py`
- a `memento-signal` CLI entry point in `pyproject.toml`

Reuse `src/memento/prediction.py` for Availability computation. If small extraction is
needed to share forecast vintages or projections, move only the deterministic shared
function and preserve existing OOS outputs and replay tests.

Publish beneath ignored `data/signals/<signal-set-id>/`:

```text
signal.parquet
signal_evidence.parquet
manifest.json
```

Update `data/signals/current.json` only after the complete set validates and publishes.
The content identity includes all source-manifest hashes, cutoff, economics input,
calculation versions, configuration hash, and carrying-rate version. Identical inputs
must replay byte-identically.

### Serving and UI

Expected implementation areas:

- `src/memento/serving.py`
- `src/memento/api.py`
- `src/memento/api_cli.py`
- `web/app/`, `web/components/`, and `web/lib/attention/`
- Python API, frontend schema, component, and Playwright tests

Expose a versioned read-only signal queue and detail endpoint. Migrate the single pane
from Attention to Memento Signal and rename frontend folders where useful; do not retain
two competing product panes. The UI must show:

- overall rank and signal-type rank;
- signal type and direction;
- native metric, economic basis, reaction window, and confidence components;
- a type-specific evidence view;
- exact run cutoff, source lineage, and calculation versions; and
- filters for all three types that preserve overall rank positions.

Keep the 3D view only if it continues to map published `impact`, `reaction`, and
`confidence` scores directly. The client must not calculate metrics, scores, rank,
economic impact, or signal eligibility.

## Build sequence

1. Version and test the expanded contracts and reason-code inventory.
2. Add canonical economics input validation using minimized synthetic fixtures.
3. Extract only the forecast/projection helpers needed by multiple signal calculations.
4. Implement pure Demand Momentum and Inventory Imbalance equations with hand-calculated
   tests before adding publication.
5. Build atomic unified signal publication and deterministic cross-type ranking.
6. Add the read-only API models and runtime-validated frontend schemas.
7. Rename and adapt the UI to the unified queue and three evidence modes.
8. Add a minimized end-to-end fixture that naturally emits all three signal types plus
   non-candidates and deterministic ties.
9. Run the full repository gate and inspect the diff for data, secrets, generated files,
   and accidental Synthetic Data changes.
10. In a separately authorized Synthetic Data task, publish the economics input, then
    run the full 90-item/2,000-store acceptance and matured evaluation.

## Acceptance checks

### Equations and eligibility

- Every new equation has hand-calculated inputs and expected outputs.
- Demand acceleration, deceleration, non-persistent movement, WAPE-band suppression,
  missing history, negative sales, and OOS censoring are independently exercised.
- Inventory excess, no excess, base-path OOS exclusion, dated inbound, cost, carrying
  rate, and low/base/high stability are independently exercised.
- Availability predictions and their existing evidence remain byte-identical when the
  same legacy inputs and versions are replayed.
- Every suppressed or failed candidate emits a contracted safe reason code in aggregate
  diagnostics without exposing source rows.

### Ranking and publication

- One fixture produces at least two candidates per signal type, plus a non-candidate for
  each type.
- Type-relative impact normalization, reaction, confidence, weights, overall ordering,
  type ordering, and all tie-breaks match hand calculations.
- The visible overall top ten contains all three types because of fixture economics, not
  quotas or post-ranking UI selection.
- Filtering never changes ranks or mutates the queue.
- Invalid economics, source, or calculation input publishes no partial signal set and
  does not move `current.json`.
- Replay is byte-identical and historical signal sets remain immutable.

### API and UI

- Python response models and frontend runtime schemas reject malformed types, decimals,
  enums, out-of-range scores, mismatched evidence, and invalid lineage.
- Every displayed business value comes from the immutable signal set, evidence, bound
  canonical dimensions, or versioned configuration.
- Revenue, contribution, inventory capital, and carrying cost use distinct labels.
- The UI never describes confidence as probability, projections as editable scenarios,
  or exposure as realized/guaranteed savings.
- Browser acceptance selects and inspects one signal of each type, verifies evidence,
  filters without renumbering, and returns to the identical queue.

### Verification

Run the narrow checks during development, then the existing complete gate:

```text
.venv/bin/pytest tests/test_metrics.py <new focused signal tests>
.venv/bin/pytest tests/e2e
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web test
npm --prefix web run build
npm --prefix web run test:e2e
npm --prefix web run test:e2e:fullstack
make verify
git diff --check
```

Report any check not run. Full-scale acceptance additionally records candidate counts
by type, top-ten composition, runtime, disk use, signal/release IDs, replay hashes, and
matured evaluation results.

## Data classification, fixtures, and lineage

- Treat retailer extracts and brand unit economics as untrusted at the boundary.
- Unit cost is confidential for real customers; it must remain in approved ignored or
  tenant-scoped storage and must not appear in logs, exceptions, committed fixtures, or
  client payloads. The UI receives only derived economic amounts required by the signal.
- Commit only small synthetic fixtures with obviously artificial costs and identities.
- Keep raw, canonical, prediction, signal, and evaluation artifacts physically distinct.
- Signal manifests must resolve to the exact Walmart, Miro extension, economics, and
  release-set checksums plus formula/configuration versions.
- Private evaluator truth remains unavailable to calculation and serving code.

## Decisions requiring explicit approval

Before full-scale completion, obtain approval for:

1. The cross-repository source-contract change that publishes
   `company_item_economics`; this plan does not authorize modifying Synthetic Data.
2. The initial versioned `annual_carrying_cost_rate`. Do not invent a customer-specific
   rate or expose it as a user-editable scenario control.
3. Any change from the proposed type-relative impact normalization or shared
   `0.50 / 0.30 / 0.20` rank weights.
4. Any production deployment, real customer data use, externally visible release, new
   persistent datastore, or access-control design.

## Builder handoff

Task name: `build-memento-signal-three-metric-mvp`

Outcome: deliver one immutable Memento Signal queue that computes, explains, and ranks
Availability Risk, Demand Momentum Gap, and Inventory Imbalance Exposure using validated
observable inputs and approved unit economics.

Acceptance checks: deterministic equations and reason codes; atomic publication; exact
lineage; correct cross-type ranking without quotas; validated API/UI contracts; one
end-to-end fixture covering all signal types; complete repository verification; no
customer data, generated artifacts, or Synthetic Data modification.

Review intent: independently verify formula fidelity, economic labeling, knowledge-time
safety, cost confidentiality, ranking determinism, immutable replay, and strict scope
before approving the MVP as full-scale ready.
