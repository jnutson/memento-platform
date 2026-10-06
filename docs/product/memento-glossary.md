# Memento Glossary — Memento Signal MVP

Status: accepted terminology for MVP implementation

Glossary version: `memento-glossary-v1.4.0`

## Purpose and authority

Memento Signal is an immutable ranked set of heterogeneous retail conditions. An
Availability Risk is projected depletion and lost retail sales. A Demand Momentum Gap
is persistent stockout-aware divergence from the retailer forecast and may represent
revenue opportunity or forecast-overstatement exposure. Inventory Imbalance Exposure
is projected inventory above a deterministic policy band; inventory capital and
carrying cost are exposure measures, not realized loss or guaranteed savings.

Company item unit cost is an approved effective-dated internal input. It is never
inferred from retailer values and never sent to the client; only contracted derived
economic amounts may be displayed.

This glossary fixes the source and derived terms used by the single MVP capability:
predicting store-item out-of-stock timing and ranking predictions by impact, reaction
time, and confidence.

Walmart source terminology is governed by the PSP Glossary in the Synthetic Data
repository at `config/reference_sources/PSP Glossary.csv`. Memento may derive qualified
measures but must not redefine an unqualified Walmart term.

## Walmart source terms preserved by Memento

| Term | Definition used by Memento | Usage constraint |
|---|---|---|
| Walmart Item Number | Walmart identifier for an item configuration used for selling, shipping, ordering, and replenishment. | It is not Miro's internal item identifier and need not be one-to-one with a consumer product. |
| Walmart year-week | Walmart merchandising year followed by its two-digit merchandising week. | Resolve from `calendar_dim`; never infer from ISO week. |
| POS quantity | Store-fulfilled units sold to customers minus returns. | Preserve signed corrections and declared channel filters. |
| POS sales | Store-fulfilled retail sales dollars minus returns. | Do not call latent demand, shipments, or estimated lost sales POS sales. |
| Store on hand | Merchandise physically at the Walmart store, excluding inventory in transit or at a DC. | The MVP receives an end-of-day book-inventory observation, not intraday shelf availability. |
| Store on order | Units ordered for a store but not yet shipped or invoiced by the DC. | Approval to ship alone does not create Store In Transit. |
| Store in transit | Units invoiced by the DC to a store but not yet received and finalized. | Do not use for approval to ship or all outstanding PO units. |
| Gross receipt quantity | Sellable units received at the store. | Keep distinct from net receipts, which subtract store returns. |
| Final forecast each quantity | Walmart's final forecast after its adjustments. | It is an input and benchmark, not the Memento demand forecast. |
| Traited store-item | A store-item represented as traited under Walmart's replenishment status. | It is assortment evidence, not proof of inventory availability. |
| Item replenishment indicator | Indicates whether the item can be replenished through the applicable Walmart process. | Non-replenishable items are ineligible for the OOS prediction queue. |
| Base unit retail | Foundational retail price before markdowns, promotions, or regional pricing. | Keep distinct from realized POS price and estimated lost-sales value. |

## Replenishment identity and lifecycle terms

| Term | Memento definition |
|---|---|
| PO line | Unique `retailer_order_id x order_line_nbr` lifecycle object. State calculations first select its latest version known at the cutoff. |
| PO-line version | Immutable PO-line observation identified by `event_version` and `known_at`; later versions supersede calculations but never overwrite history. |
| Approval to ship | Observable operational precursor that remains Store On Order until DC invoice evidence exists. |
| Open-order units | For the latest non-cancelled PO-line version, `max(ordered_qty - invoiced_qty, 0)`. |
| In-transit units | For the latest non-cancelled PO-line version, `max(invoiced_qty - received_qty, 0)`. |
| Pipeline units | Deduplicated open-order plus in-transit units; equivalently `max(ordered_qty - received_qty, 0)` under valid lifecycle quantities. |
| Scheduled inbound units | Pipeline units grouped by the latest expected store receipt date known at the prediction cutoff. |
| Overdue inbound units | Pipeline units expected on or before the observation date without a finalized receipt; excluded from projected supply. |
| Daily receipt units | Positive change in cumulative received units posted for a business date and reconciled to Walmart Gross Receipt Quantity. |
| Inbound reconciliation rate | Maximum of independently calculated open-order, in-transit, and receipt reconciliation rates after PO-line version deduplication. |

A partially invoiced PO line may contain both open-order and in-transit units. Those are
disjoint portions of one order, not duplicate quantities. Repeated versions or extracts
of the same PO line are aliases and must be deduplicated before aggregation.

## Memento observed and forecast terms

| Term | Memento definition |
|---|---|
| Prediction as of | Immutable UTC cutoff for every source row, revision, and calculation used by a run. |
| Latest fully closed business date | Latest store-local business date whose close is observable at the prediction cutoff. It is derived per store timezone, not from the UTC calendar date alone. |
| Observation date | Latest fully closed store business date eligible at `prediction_as_of`. |
| Net sales units | Sum of validated POS quantities for a store, item, and business date; returns and corrections remain signed. |
| Net sales amount | Sum of validated POS sales dollars over the same population as net sales units. |
| Realized unit price | Net sales amount divided by positive net sales units, otherwise the declared eligible retail-price fallback. |
| Ending on-hand units | Validated end-of-day Walmart Store On Hand quantity. |
| Observed OOS day | Day ending with zero book on hand while the item is assorted, replenishment-enabled, and the location is open. |
| Eligible retailer forecast | Latest Walmart Final Forecast Each Quantity created before the target Walmart week and known by the cutoff. |
| Memento demand forecast | Frozen versioned estimate of future consumer sell-through derived from prior eligible observations. It is not a Walmart forecast. |
| Forecast WAPE | Sum of absolute forecast errors divided by sum of eligible actual units. |
| Forecast bias | Sum of forecast minus actual divided by sum of eligible actual units; positive is overforecast. |
| Forecast error band | Historical WAPE clamped to `[0,1]` and used as the visible multiplier around base demand. It is not a probability or prediction interval. |
| Low demand path | Base daily demand multiplied by `1 - forecast_error_band`, floored at zero. |
| Base demand path | Bias-adjusted retailer weekly forecast allocated by observed weekday share. |
| High demand path | Base daily demand multiplied by `1 + forecast_error_band`. |
| Projected on hand | Deterministic inventory path starting from observed on hand, adding eligible inbound once, and subtracting the named demand path. |

## OOS prediction and ranking terms

| Term | Memento definition |
|---|---|
| Predicted OOS date | First depletion date on the deterministic base inventory path. It is a prediction, not an observed Walmart field. |
| Earliest OOS date | First depletion date on the high-demand sensitivity path. It is a bound, not a probability statement. |
| Latest OOS date | First depletion date on the low-demand sensitivity path; it is null when that path does not deplete within 28 days. |
| Estimated lost units | Unfulfilled base-path demand after projected depletion. It is an estimate, not observed sales. |
| Estimated lost sales | Estimated lost units valued at the eligible unit price and rounded only at publication. It is not Walmart POS sales. |
| Impact score | Within-run normalized score based on estimated lost retail sales. |
| Minimum reaction days | Configured time Miro Toys needs to react before predicted depletion. It is not end-to-end product lead time. |
| Action slack days | Calendar days until predicted OOS minus minimum reaction days; negative means late to prevent. |
| Reaction score | Versioned urgency multiplied by the feasibility factor derived from action slack. |
| Data completeness | Versioned weighted coverage and reconciliation quality of the evidence required for prediction. |
| Timing stability score | One minus the earliest-to-latest OOS date span divided by 28; zero when a sensitivity bound does not deplete. |
| Prediction confidence score | Weighted average of forecast quality, data completeness, and timing stability. It is not a probability. |
| Rank score | Weighted combination of impact, reaction, and confidence used to order eligible predictions. |
| Top-10 queue | At most ten eligible predictions ordered by rank score and deterministic tie-breaks; it is a display limit, not an admission threshold. |

## Release terminology

| Term | Memento definition |
|---|---|
| Package content manifest | Deterministic inventory and checksums for one immutable Walmart or Miro extension package. It excludes execution IDs, wall-clock timestamps, and host-specific paths. |
| Release-set manifest | Deterministic manifest binding one Walmart package-manifest checksum to its exact Miro extension package-manifest checksum, cutoff, configuration hash, and controlling contract versions. It is the only supported discovery target. |
| Release-set pointer | Atomically updated `current.json` reference to a validated release-set manifest. It never points directly to an individual package. |

## Terminology constraints

- Low/base/high paths are fixed arithmetic sensitivity checks, not Monte Carlo draws,
  probabilities, prediction intervals, or interactive scenarios.
- Do not call approval-to-ship quantity **in transit** without DC invoice evidence.
- Do not add raw Store On Order and Store In Transit until PO-line versions are resolved
  and quantities are known to be disjoint.
- Do not call projected inventory actual inventory.
- Do not call estimated lost sales POS sales or realized loss.
- Do not call end-of-day zero book inventory an intraday shelf OOS.
- Do not call a Memento demand forecast a Walmart forecast.
- Do not describe a confidence score or sensitivity bound as a probability.
