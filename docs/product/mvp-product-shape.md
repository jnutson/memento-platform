# Memento Signal Three-Metric MVP — Product Shape

Status: accepted product direction
Contract version: `memento-signal-product-v1.0.0`

The formulas and numeric defaults behind this product shape are defined in
`docs/product/mvp-metric-contract.md`. Terms are governed by
`docs/product/memento-glossary.md`; Walmart source terms retain their PSP Glossary
meanings.

## Single product capability

Memento Signal presents one immutable ranked queue containing Availability Risk,
Demand Momentum Gap, and Inventory Imbalance Exposure. Every row preserves its native
metric and economic basis. Impact normalization occurs within signal type; reaction and
confidence use shared definitions. Overall ranks are assigned before the top-ten limit,
and filtering never recomputes or renumbers them.

The persisted grain is `signal_as_of x store_id x product_id x signal_type x
signal_episode`. Type order for deterministic ties is `availability`,
`demand_momentum`, `inventory_imbalance`. The interface distinguishes revenue
opportunity, contribution impact, inventory capital, and carrying-cost exposure.

### Availability compatibility

Memento predicts when a scoped Miro Toys item at a Walmart store will go out of stock
within the next 28 days and ranks eligible predictions using exactly three dimensions:

1. Estimated lost retail sales impact.
2. Remaining reaction time.
3. Prediction confidence.

The user receives one deterministic daily queue containing at most 10 store-item OOS
predictions. Each prediction answers: what item and store are at risk, when depletion is
predicted, how much retail sales exposure is estimated, how much time remains to react,
how confident Memento is, and why the item received its rank.

This milestone is not a general insights platform, scenario-planning product,
replenishment recommendation system, or supply-planning application.

## Fixed test case

- Company: `MIRO_TOYS`, displayed as **Miro Toys**.
- Retailer: synthetic Walmart US.
- Source brand: `BRAND_A`.
- Display brand: **Miro Spark**, mapped without rewriting the retailer source brand.
- Portfolio: all 90 configured `BRAND_A` items.
- Locations: all 2,000 stores in the checked target reference snapshot.
- Observable coverage: Walmart FY2027 through FY2028; FY2026 is retained only as
  internal comparable support, and future facts remain private until
  their release cutoff.
- Initial prediction cutoff: `2027-01-30T12:00:00Z`, after every included store has
  closed January 29 in local time.
- Prediction horizon: 28 calendar days.
- User-visible output: at most 10 ranked predictions per daily run.

The Brand A item set and store-reference snapshot are reviewed, hashed inputs. Selection
must never depend on row order or on which cases produce the most favorable result.

## Focused pipeline

```text
validated observable inputs
        |
        v
bias-adjusted forecast + historical WAPE band
        |
        v
inventory projection with dated inbound
        |
        v
base OOS date, sensitivity range, and estimated lost sales
        |
        v
impact + reaction + confidence scoring
        |
        v
deterministic ranked top 10
```

These are narrow stages inside one daily OOS prediction job. They are not generalized
platform engines. The same accepted source releases, cutoff, configuration, and calculation
versions must reproduce identical predictions, scores, and ordering.

The forecast is deliberately interpretable. Historical WAPE creates deterministic
low/base/high demand paths; there is no random sampling, Monte Carlo simulation,
black-box model, or interactive scenario-planning capability.

## Ranked prediction contract

The ranked unit is one predicted store-item OOS episode at:

```text
prediction_as_of x store_id x product_id x predicted_episode
```

Required fields:

```text
prediction_id
prediction_as_of
company_id
brand_id
store_id
product_id
predicted_oos_date
earliest_oos_date                       nullable
latest_oos_date                         nullable
estimated_lost_units
estimated_lost_sales_amount
days_until_predicted_oos
minimum_reaction_days
action_slack_days
forecast_wape
forecast_error_band
forecast_quality
data_completeness
oos_date_span_days                       nullable
timing_stability_score
impact_score
reaction_score
prediction_confidence_score
rank_score
rank_position
source_release_ids
source_release_set_id
metric_contract_version
demand_forecast_version
inventory_projection_version
ranker_version
configuration_hash
```

The default display shows the item, store, base predicted OOS date, low/high sensitivity
range, estimated lost sales, remaining reaction time, confidence, rank, and the three
component scores. A compact calculation trace exposes the source values and arithmetic.
It does not provide a probability or recommended action.

## Capability requirements

### 1. Validate inputs

Before prediction, validate:

- Exact schemas, types, keys, enums, date bounds, manifests, and hashes.
- Miro-to-Walmart item mappings and configured cohort membership.
- Nonnegative inventory, replenishment, price, and forecast quantities.
- PO-line identity, lifecycle quantities, expected dates, receipt dates, and versions.
- Independent reconciliation of on-order, in-transit, and receipt quantities.
- Knowledge-time safety at `prediction_as_of`.
- Exactly one applicable reaction constraint per scoped item.

If any required source fails for the configured cohort, publish no prediction set. Logs
contain identifiers, versions, checks, counts, and reason codes—not source rows.

### 2. Forecast demand and project inventory

For every scoped store-item:

- Select only retailer forecasts created before their target Walmart week.
- Freeze a Memento demand-forecast vintage using prior observable POS, calendar effects,
  and eligible retailer forecast values.
- Estimate bias, weekday distribution, and WAPE from strictly prior eligible
  forecast-versus-actual history.
- Start from the latest eligible end-of-day on-hand value.
- Add each eligible, deduplicated, future-dated inbound quantity once on its expected
  store receipt date.
- Calculate transparent low/base/high daily demand as base demand multiplied by
  `1 - WAPE`, `1`, and `1 + WAPE`, with WAPE clamped to `[0,1]`.
- Project inventory independently for the three named paths over 28 days.
- Use the base path for the predicted date and estimated loss; use high/low paths for
  earliest/latest sensitivity dates and timing stability.

All calculations are deterministic arithmetic and first-date lookups.

### 3. Generate and rank OOS predictions

A store-item becomes eligible when:

- The deterministic base path depletes within 28 days.
- Base-path estimated lost sales are positive.
- Data completeness meets the trust threshold.
- The item is active, assorted, and replenishment-enabled at the store.

There is no lost-sales-dollar admission threshold. Every eligible base-path depletion
is persisted for audit, ranked, and then truncated to the top 10 for display.

The three rank dimensions are:

```text
impact_score
  = within-run normalized estimated lost retail sales

reaction_score
  = urgency based on predicted OOS date
    * feasibility based on minimum reaction days

prediction_confidence_score
  = 0.50 * forecast quality
    + 0.30 * data completeness
    + 0.20 * low/base/high timing stability

rank_score
  = 0.50 * impact_score
  + 0.30 * reaction_score
  + 0.20 * prediction_confidence_score
```

Tie-break by higher estimated lost sales, earlier predicted OOS date, store ID, then
product ID. Raw dates, WAPE, sensitivity range, action slack, and confidence components
remain visible alongside the scores.

### 4. Publish immutable results

- A run publishes one complete prediction set or nothing.
- Walmart and matched Miro source packages are accepted only through one atomically
  published release-set manifest; neither package is independently discoverable.
- Identical accepted inputs and versions replay byte-identically.
- New source releases create new immutable forecast and prediction versions.
- Historical predictions are never recomputed in place.
- Every displayed value resolves to the release-set manifest, both package-manifest
  checksums, cutoff, configuration, and metric, forecast, projection, and ranker
  versions.
- Private synthetic truth is never available to prediction code or user output.

## Required observable inputs

Existing Walmart schemas:

- `calendar_dim`
- `store_dim`
- `omni_item_dimensions`
- `store_sales`
- `store_invt`
- `long_rng_store_dmd_frcst`

The current accepted Walmart release remains immutable and is not the Miro OOS base. A
new two-year Brand A run must retain the six schemas while applying the
glossary-aligned replenishment semantics and cutoff-safe release projection.

Required focused extensions:

- Minimal `dim_item` mapping for Miro Toys/Miro Spark identity and Walmart item linkage.
- `retailer_replenishment_commitment` for deduplicated PO-line versions, DC invoice
  state, expected store receipt date, and actual receipts.
- `item_reaction_constraint` for minimum reaction days.

No planogram, store/DC topology, DC inventory, cost, case-pack, dimension, promotion, or
supply-network input is required for this capability.

## Offline evaluation boundary

Later observable inventory, receipts, and POS are used only to evaluate matured frozen
predictions. MVP verification measures whether OOS occurred within the horizon,
prediction-date error and precision at 10. Private synthetic
latent demand may evaluate lost-unit estimates outside the product boundary.

Evaluation is an acceptance and model-quality harness, not a human-feedback feature or
a second user-facing capability.

## Explicitly deferred

- Interactive scenario planning or user-controlled what-if inputs.
- Promotion response, price elasticity, assortment, and shelf-space analysis.
- Weekly trend, historical OOS exposure, gross margin, or general insight catalogs.
- Recommended actions, purchase quantities, order changes, allocation, or execution.
- DC inventory feasibility and retailer network topology.
- Human feedback capture, online learning, or personalized ranking.
- Intraday shelf availability; this MVP predicts end-of-day store-item depletion.
- Multiple retailers, companies, brands, or unrestricted item/store cohorts.
- Miro factory, production, port, carrier, import, company-DC, or supply-plan worlds.

## Acceptance criteria

1. A daily run deterministically publishes zero or more immutable OOS prediction rows
   and a stable top-10 ordering.
2. Every prediction has reproducible low/base/high paths, a base predicted date,
   estimated lost sales, and impact, reaction, confidence, and composite scores.
3. Fixtures independently exercise high/low impact, reaction time, and confidence, plus
   a store-item that does not deplete and therefore produces no candidate.
4. At least one frozen prediction precedes a later observable OOS, allowing prediction
   timing to be evaluated without future leakage.
5. Ranking uses only impact, reaction, and confidence with the declared weights and
   deterministic tie-breaks.
6. Every displayed value traces to one immutable release set, its exact Walmart and
   extension manifest checksums, and calculation versions.
7. Invalid required inputs or a calculation failure publish no prediction set.
8. Replay is byte-identical, logs contain no source rows, generated data remains
   ignored, and private truth remains inaccessible.
9. No probability model, random sampling, Monte Carlo simulation, interactive scenario
   control, recommended action, secondary insight, DC feasibility, planogram, or
   feedback-loop feature is required or presented as MVP.
