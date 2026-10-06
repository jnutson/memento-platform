# Memento Signal Three-Metric MVP — Metric Contract

Status: accepted for MVP implementation
Contract version: `memento-signal-metrics-v1.0.0`

## Purpose

The common rank is `0.50 * type_relative_impact + 0.30 * reaction + 0.20 *
confidence`. Midrank normalization is independent within each signal type. Primary
economics are lost retail sales for Availability, absolute contribution impact for
Demand Momentum, and inventory capital plus 28-day carrying cost for Inventory
Imbalance. Missing economics remain null.

Demand Momentum uses six baseline and two recent completed weeks, requires both recent
weeks to diverge in the same direction, clamps the recent/baseline multiplier to
`[0.50,1.50]`, and suppresses gaps not exceeding the historical WAPE band. Inventory
Imbalance uses `ceil(7 * clamped_wape)` safety days and a target cover equal to minimum
reaction plus safety days; base-path OOS suppresses the excess signal. The carrying
rate and its version are required publication inputs; no default is invented, and the
rate is not a UI control or a customer-specific assumption.

This document is the mathematical source of truth for the single MVP capability:
predicting a store-item out-of-stock date and ranking eligible predictions by estimated
lost-sales impact, reaction time, and confidence.

Every calculation is deterministic and expressible as an ordinary arithmetic equation,
aggregation, or first-date lookup. The MVP uses no Monte Carlo simulation, random
sampling, black-box forecasting, optimization, or interactive scenario engine.

Changing a formula, input rule, threshold, fallback, or meaning requires a new contract
version and explicit review. Business terms are governed by
`docs/product/memento-glossary.md`; Walmart terms retain their PSP Glossary meanings.

## Fixed scope and defaults

- Company `MIRO_TOYS` and display brand `MIRO_SPARK`.
- All 90 configured `BRAND_A` items across all 2,000 stores in the checked target
  reference snapshot.
- Store-item-day prediction grain.
- 28-calendar-day horizon.
- At most 10 displayed predictions per daily run.
- Eight completed Walmart weeks of forecast history.
- Six eligible item-store forecast/actual pairs; 20 observations for pooled fallbacks.
- Rank weights: impact `0.50`, reaction `0.30`, confidence `0.20`.
- Late-to-prevent feasibility factor: `0.25`.
- Minimum data completeness: `0.50`.
- Maximum accepted inbound reconciliation rate: `0.10`.

There is no OOS-probability or lost-sales-dollar admission threshold. The deterministic
base inventory path either depletes within the horizon or it does not.

## Global conventions

### Time

- `prediction_as_of` is the immutable UTC cutoff of the accepted source set.
- `prediction_date` is the store-local date at that cutoff.
- `observation_date` is the latest fully closed store business date. The initial
  `2027-01-30T12:00:00Z` cutoff resolves to January 29, 2027 for every included
  contiguous-US store.
- Horizon day 1 is `observation_date + 1`.
- No source row or version with `known_at > prediction_as_of` is eligible.
- Walmart weeks and comparable dates come only from the validated calendar.

### Numeric behavior

- Calculations use `DOUBLE` internally.
- Published unit estimates use `DECIMAL(20,6)`.
- Currency uses unrounded inputs and rounds half-even to `DECIMAL(20,2)` only at output.
- Scores use `[0,1]` and publish as `DECIMAL(9,6)`.
- Division by zero returns `NULL` with a reason code.
- Missing values remain missing unless a fallback is explicitly declared.
- Negative inventory or replenishment quantities make the grain ineligible; they are not
  clamped to zero.

### Required lineage

Every published prediction carries or resolves through its manifest to:

```text
source_release_ids
source_release_set_id
metric_contract_version
demand_forecast_version
inventory_projection_version
ranker_version
configuration_hash
prediction_as_of
```

## 1. Observed deterministic metrics

### M-001 `net_sales_units`

```text
net_sales_units[s,i,d] = sum(sales_quantity)
```

Use validated `sales_daily` rows for included channels and retail types. Returns and
corrections remain signed.

### M-002 `net_sales_amount`

```text
net_sales_amount[s,i,d] = sum(sales_amount)
```

Use the identical row population as M-001 and require USD.

### M-003 `units_for_demand_model`

```text
units_for_demand_model =
    net_sales_units when net_sales_units >= 0
    NULL otherwise
```

Negative net-sales days are excluded with reason `negative_net_sales`; canonical sales
remain unchanged.

### M-004 `realized_unit_price`

```text
if net_sales_units > 0:
    realized_unit_price = net_sales_amount / net_sales_units
else:
    realized_unit_price = inventory_daily.current_unit_retail_amount
```

Negative or missing results return `NULL` with `invalid_or_missing_price`.

### M-005 `ending_on_hand_units`

```text
ending_on_hand_units = inventory_daily.on_hand_quantity
```

This is end-of-day book inventory, not intraday shelf availability.

### M-006 `observed_oos_day`

```text
observed_oos_day =
    ending_on_hand_units = 0
    AND assorted = true
    AND replenishment_enabled = true
    AND location is open
```

Missing or negative inventory returns `NULL`, not `false`.

### M-007 `open_order_units`

Select the latest version known at the cutoff for each
`retailer_order_id x order_line_nbr`.

```text
open_order_units =
    0                                             when status = cancelled
    max(ordered_qty - invoiced_qty, 0)           otherwise
```

Aggregate at store-item-cutoff grain.

### M-008 `in_transit_units`

```text
in_transit_units =
    0                                             when status = cancelled
    max(invoiced_qty - received_qty, 0)           otherwise
```

Walmart Store In Transit begins at DC invoice, not approval to ship.

### M-009 `scheduled_inbound_units`

For each latest eligible non-cancelled PO line:

```text
pipeline_units = open_order_units + in_transit_units
               = max(ordered_qty - received_qty, 0)

scheduled_inbound_units[expected_store_receipt_date] = sum(pipeline_units)
```

Include only non-null expected receipt dates after `observation_date`. Quantity expected
on or before the observation date without a finalized receipt is `overdue_inbound_units`
and is excluded from projected supply.

### M-010 inbound reconciliation

At store-item-observation-date grain:

```text
open_order_difference = open_order_units - on_order_quantity
in_transit_difference = in_transit_units - in_transit_quantity

derived_receipt_units =
    sum(positive received_qty changes posted on observation_date)

receipt_difference = derived_receipt_units - receipt_quantity
```

For each state:

```text
reconciliation_rate =
    abs(derived - snapshot) / max(derived, snapshot, 1)
```

```text
inbound_reconciliation_rate = max(
    open_order_reconciliation_rate,
    in_transit_reconciliation_rate,
    receipt_reconciliation_rate
)
```

A rate above `0.10` fails source acceptance. A nonzero accepted rate reduces data
completeness. Historical PO reconciliation is required only within the extension's
declared trailing 56-day retention window; M-010 remains mandatory at the observation
date.

## 2. Interpretable demand forecast

### Eligible completed week

A store-item Walmart week is eligible only when all seven sales and inventory days are
present, inventory is nonnegative, the item is active/assorted/replenishable, no day is
an observed OOS day, net sales are nonnegative, and the week ended before the forecast
cutoff.

### M-011 `actual_eligible_weekly_units`

```text
actual_eligible_weekly_units[s,i,w] =
    sum(units_for_demand_model[s,i,d]) for d in eligible week w
```

### M-012 `eligible_retailer_forecast`

For a target week, select the retailer forecast with the greatest creation week that is
strictly earlier than the target week and known by `prediction_as_of`.

### M-013 `forecast_bias_factor`

Use the eight most recent eligible completed weeks:

```text
raw_bias_factor =
    sum(actual_eligible_weekly_units)
    / sum(eligible_retailer_forecast)

forecast_bias_factor = clamp(raw_bias_factor, 0.50, 1.50)
```

Require six item-store pairs and a positive forecast denominator. Fallback order:

1. Same store-item.
2. Same item across configured stores, requiring 20 observations.
3. Miro Spark cohort across configured stores, requiring 20 observations.
4. `1.0` with `no_bias_history`.

### M-014 `memento_weekly_demand_base`

```text
memento_weekly_demand_base =
    eligible_retailer_forecast * forecast_bias_factor
```

The value is nonnegative and frozen with the forecast vintage.

### M-015 `weekday_share`

Using the same eligible history:

```text
weekday_share[j] =
    sum(units_for_demand_model on weekday j)
    / sum(units_for_demand_model across all weekdays)
```

Require four positive-total weeks. Fallback from store-item to item, then brand, then
uniform `1/7`. Normalize shares to sum exactly to `1.0`.

### M-016 `daily_demand_base`

```text
daily_demand_base[s,i,d] =
    memento_weekly_demand_base[s,i,week(d)]
    * weekday_share[s,i,weekday(d)]
```

### M-017 forecast error metrics

For frozen historical Memento forecasts after the target week closes:

```text
forecast_error_units = actual - forecast

forecast_wape = sum(abs(actual - forecast)) / sum(actual)

forecast_bias = sum(forecast - actual) / sum(actual)
```

Use six pairs and the M-013 fallback hierarchy. A zero actual denominator returns
`NULL` with `insufficient_actual_units`.

## 3. Transparent uncertainty band

### M-018 `forecast_error_band`

```text
if forecast_wape is not null:
    forecast_error_band = clamp(forecast_wape, 0, 1)
else:
    forecast_error_band = 1
```

The fallback produces the widest permitted band and zero forecast quality. It is
deliberately conservative and fully visible.

### M-019 low/base/high daily demand paths

```text
daily_demand_path[low,d] =
    max(daily_demand_base[d] * (1 - forecast_error_band), 0)

daily_demand_path[base,d] = daily_demand_base[d]

daily_demand_path[high,d] =
    daily_demand_base[d] * (1 + forecast_error_band)
```

These are deterministic sensitivity bounds, not probabilities, prediction intervals,
or user-configurable scenarios.

## 4. Deterministic inventory projection

For each named path `p in {low, base, high}` and horizon date `d`:

### M-020 inventory balance

```text
opening_units[p,d] =
    starting_on_hand_units                         when d is day 1
    projected_ending_on_hand_units[p,d-1]          otherwise

available_units[p,d] = opening_units[p,d] + scheduled_inbound_units[d]

fulfilled_units[p,d] = min(available_units[p,d], daily_demand_path[p,d])

lost_units[p,d] = max(daily_demand_path[p,d] - available_units[p,d], 0)

projected_ending_on_hand_units[p,d] =
    max(available_units[p,d] - daily_demand_path[p,d], 0)
```

Inbound is available at the start of its expected date and demand consumes inventory
after inbound. Every eligible inbound quantity is added once.

### M-021 path OOS dates

```text
oos_date_p =
    first date projected_ending_on_hand_units[p,d] = 0
    NULL when no such date exists in the horizon
```

Because high demand is never below base and low demand is never above base, valid dates
must order as `high <= base <= low` when all three exist.

### M-022 `predicted_oos_date`

```text
predicted_oos_date = oos_date_base
earliest_oos_date = oos_date_high
latest_oos_date = oos_date_low
```

The base-path date is the prediction. Earliest/latest are transparent sensitivity
bounds; a missing latest date means the low-demand path does not deplete within 28 days.

## 5. Estimated lost-sales impact

### M-023 estimated lost units and sales

Use only the deterministic base path:

```text
estimated_lost_units = sum(lost_units[base,d])

applicable_unit_price =
    latest valid realized_unit_price known at prediction_as_of

estimated_lost_sales_amount =
    estimated_lost_units * applicable_unit_price
```

Hold price constant across the horizon. The output is an estimate, not realized loss.

### M-024 `impact_score`

Across eligible candidates before top-10 truncation, rank ascending by
`ln(1 + estimated_lost_sales_amount)` using average rank for ties:

```text
impact_score = 1                                      when candidate_count = 1

impact_score =
    (ascending_average_rank - 1) / (candidate_count - 1)
    otherwise
```

This is a within-run prioritization score, not a longitudinal index.

## 6. Reaction timing

### M-025 reaction metrics

```text
days_until_predicted_oos = predicted_oos_date - prediction_date

action_slack_days =
    days_until_predicted_oos - minimum_reaction_days

urgency_score =
    1 - clamp(days_until_predicted_oos / 28, 0, 1)

feasibility_factor =
    1.00 when action_slack_days >= 0
    0.25 when action_slack_days < 0

reaction_score = urgency_score * feasibility_factor
```

Negative slack is labeled `late_to_prevent`; it is not suppressed.

## 7. Interpretable confidence

### M-026 `data_completeness`

```text
sales_coverage = present valid sales days / expected sales days
inventory_coverage = present valid inventory days / expected inventory days
forecast_pair_coverage = min(eligible forecast/actual pairs / 6, 1)
inbound_quality = 1 - clamp(inbound_reconciliation_rate, 0, 1)

data_completeness =
    0.30 * sales_coverage
  + 0.30 * inventory_coverage
  + 0.25 * forecast_pair_coverage
  + 0.15 * inbound_quality
```

### M-027 `forecast_quality`

```text
forecast_quality =
    1 - clamp(forecast_wape, 0, 1)     when forecast_wape is not null
    0                                  otherwise
```

### M-028 `timing_stability_score`

```text
if predicted_oos_date is null:
    timing_stability_score = NULL
else if earliest_oos_date is null or latest_oos_date is null:
    timing_stability_score = 0
else:
    oos_date_span_days = latest_oos_date - earliest_oos_date
    timing_stability_score = 1 - clamp(oos_date_span_days / 28, 0, 1)
```

### M-029 `prediction_confidence_score`

```text
prediction_confidence_score =
    0.50 * forecast_quality
  + 0.30 * data_completeness
  + 0.20 * timing_stability_score
```

This is an interpretable prioritization score, not a probability. Display its three
components alongside it. If `data_completeness < 0.50`, suppress the prediction and emit
`data_completeness_below_threshold`.

## 8. Candidate generation and ranking

### M-030 eligible OOS prediction

A store-item is eligible when all are true:

```text
predicted_oos_date is not null
estimated_lost_sales_amount > 0
data_completeness >= 0.50
item is active, assorted, and replenishment-enabled on observation_date
```

### M-031 `rank_score`

```text
rank_score =
    0.50 * impact_score
  + 0.30 * reaction_score
  + 0.20 * prediction_confidence_score
```

Sort descending by `rank_score`, then by:

1. Higher `estimated_lost_sales_amount`.
2. Earlier `predicted_oos_date`.
3. Ascending `store_id`.
4. Ascending `product_id`.

Assign rank before displaying positions 1–10. Persist every eligible candidate for
audit. The display limit must not manufacture candidates.

## 9. Offline evaluation

Evaluation begins only after the complete 28-day horizon is observable. It verifies the
model; it is not a second product capability.

### M-032 `oos_outcome`

```text
oos_outcome =
    any observed_oos_day = true during horizon days 1 through 28
```

Missing or invalid required inventory days return `NULL`.

### M-033 `precision_at_10`

```text
precision_at_10 =
    displayed predictions with observable OOS
    / evaluable displayed predictions
```

### M-034 lead-time error

For true positives:

```text
actual_first_oos_date = first observed_oos_day in the horizon
lead_time_error_days = predicted_oos_date - actual_first_oos_date
absolute_lead_time_error_days = abs(lead_time_error_days)
```

Observable data cannot reveal exact lost demand. Exact lost-unit error is permitted only
inside the physically separate synthetic evaluator.

## 10. Publication and no-drift rules

- Every formula is independently testable with hand-calculated fixtures.
- No random-number generator or stochastic dependency is permitted.
- No calculation reads private evaluator truth.
- Source-validation or calculation failure publishes no partial prediction set.
- Identical sources, cutoff, configuration, code, and contract versions reproduce
  identical output bytes and ordering.
- Content manifests exclude wall-clock timestamps, execution IDs, host paths, and other
  run-specific values; those belong only in separate execution metadata.
- A source set is eligible only through an atomically published release-set manifest
  binding the exact Walmart and Miro extension manifest checksums.
- Forecast and prediction versions are append-only and never recomputed in place.
- Logs contain IDs, versions, counts, durations, and reason codes—not source rows.

## 11. Required reason codes

```text
negative_net_sales
negative_inventory
invalid_or_missing_price
missing_sales_day
missing_inventory_day
item_not_active
item_not_assorted
replenishment_disabled
observed_oos_censoring
insufficient_item_store_history
pooled_item_history
pooled_brand_history
no_bias_history
default_weekday_share
insufficient_actual_units
insufficient_forecast_history
overdue_inbound
inbound_reconciliation_degraded
data_completeness_below_threshold
```

## 12. Acceptance tests

1. Every equation has hand-computed inputs and expected outputs.
2. Future knowledge and same-week retailer forecasts are rejected.
3. Forecast fallback selection is deterministic and emits the correct reason code.
4. Low/base/high demand and inventory paths reproduce exactly without randomness.
5. Path ordering and OOS date ordering invariants hold.
6. Dated inbound enters once on its eligible date; overdue/cancelled inbound never enters.
7. Impact, reaction, confidence, rank weights, and tie-breaks match exactly.
8. Fixture cases independently isolate impact, reaction, confidence, and non-depletion.
9. Later observable data evaluates only frozen prior predictions.
10. No probability, Monte Carlo, stochastic simulation, interactive scenario, or
    recommended-action calculation exists in the MVP.
11. Any invalid required source or failed calculation publishes nothing downstream.
