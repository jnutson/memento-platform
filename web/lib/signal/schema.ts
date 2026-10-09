import { z } from "zod";

export const SIGNAL_API_CONTRACT_VERSION = "memento-signal-api-v1" as const;
const decimal = z.string().regex(/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/);
const money = decimal.nullable();
const score = decimal.refine((value) => Number(value) >= 0 && Number(value) <= 1);
const signalType = z.enum(["availability", "demand_momentum", "inventory_imbalance"]);
const identity = z.strictObject({ item_name: z.string(), company_item_id: z.string(), source_product_id: z.string(), store_name: z.string(), source_location_id: z.string() });

const signalObjectSchema = z.strictObject({
  signal_id: z.string().regex(/^sig_[0-9a-f]{64}$/), signal_type: signalType,
  signal_direction: z.enum(["risk", "acceleration", "deceleration", "excess"]),
  observation_date: z.iso.date(), store_id: z.string(), product_id: z.string(), identity,
  headline_metric_name: z.string(), headline_metric_value: decimal,
  estimated_retail_sales_impact_amount: money, estimated_contribution_impact_amount: money,
  estimated_cost_impact_amount: money, inventory_cost_exposed_amount: money, carrying_cost_28d_amount: money,
  economic_impact_basis: z.string(), days_until_material_impact: z.number().int().min(1).max(28),
  minimum_reaction_days: z.number().int().nonnegative(), action_slack_days: z.number().int(),
  impact_score: score, reaction_score: score, confidence_score: score, rank_score: score,
  overall_rank_position: z.number().int().positive(), signal_type_rank_position: z.number().int().positive(),
});

function validateSignalFields(value: z.infer<typeof signalObjectSchema>, context: z.RefinementCtx) {
  const directions = { availability: ["risk"], demand_momentum: ["acceleration", "deceleration"], inventory_imbalance: ["excess"] } as const;
  if (!(directions[value.signal_type] as readonly string[]).includes(value.signal_direction)) context.addIssue({ code: "custom", path: ["signal_direction"], message: "Direction must match signal type" });
  const inventoryValues = [value.estimated_cost_impact_amount, value.inventory_cost_exposed_amount, value.carrying_cost_28d_amount];
  if (value.signal_type === "inventory_imbalance") {
    if (value.estimated_retail_sales_impact_amount !== null || value.estimated_contribution_impact_amount !== null || inventoryValues.some((item) => item === null)) context.addIssue({ code: "custom", path: [], message: "Inventory economics must match signal type" });
  } else if (value.estimated_retail_sales_impact_amount === null || value.estimated_contribution_impact_amount === null || inventoryValues.some((item) => item !== null)) context.addIssue({ code: "custom", path: [], message: "Sales economics must match signal type" });
}

export const signalSchema = signalObjectSchema.superRefine(validateSignalFields);

export const signalQueueSchema = z.strictObject({
  api_contract_version: z.literal(SIGNAL_API_CONTRACT_VERSION),
  run: z.strictObject({
    signal_set_id: z.string(), signal_as_of: z.iso.datetime({ offset: true }), candidate_count: z.number().int().nonnegative(),
    display_count: z.number().int().min(0).max(10), candidate_counts_by_type: z.record(signalType, z.number().int().nonnegative()),
    canonical_dataset_id: z.string(), source_release_set_id: z.string(), source_release_ids: z.array(z.string()),
    metric_contract_version: z.string(), signal_publication_version: z.string(), ranker_version: z.string(), configuration_hash: z.string(),
  }),
  signals: z.array(signalSchema).max(10),
}).superRefine((value, context) => {
  if (Object.values(value.run.candidate_counts_by_type).reduce((sum, count) => sum + count, 0) !== value.run.candidate_count) context.addIssue({ code: "custom", path: ["run", "candidate_counts_by_type"], message: "Candidate counts must reconcile" });
  const ranks = new Set<number>();
  for (let index = 1; index < value.signals.length; index += 1) {
    if (value.signals[index].overall_rank_position <= value.signals[index - 1].overall_rank_position) context.addIssue({ code: "custom", path: ["signals", index], message: "Overall ranks must remain ordered" });
  }
  value.signals.forEach((signal, index) => { if (ranks.has(signal.overall_rank_position)) context.addIssue({ code: "custom", path: ["signals", index, "overall_rank_position"], message: "Overall ranks must be unique" }); ranks.add(signal.overall_rank_position); });
});

const evidence = z.strictObject({
  signal_id: z.string().regex(/^sig_[0-9a-f]{64}$/), evidence_type: z.enum(["historical_week", "forward_demand", "inventory_projection"]),
  evidence_date: z.iso.date(), path: z.enum(["low", "base", "high"]).nullable(), actual_units: money,
  retailer_forecast_units: money, adjusted_forecast_units: money, demand_units: money,
  scheduled_inbound_units: money, opening_units: money, ending_units: money, lost_units: money, target_units: money,
});

export const signalDetailSchema = z.strictObject({
  api_contract_version: z.literal(SIGNAL_API_CONTRACT_VERSION),
  signal: signalObjectSchema.extend({ signal_as_of: z.iso.datetime({ offset: true }), company_id: z.string(), brand_id: z.string(), forecast_quality: score, data_completeness: score, stability_score: score, source_release_ids: z.array(z.string()), source_release_set_id: z.string(), canonical_dataset_id: z.string(), metric_contract_version: z.string(), signal_publication_version: z.string(), ranker_version: z.string(), configuration_hash: z.string() }).superRefine(validateSignalFields),
  evidence: z.array(evidence),
}).superRefine((value, context) => {
  if (value.evidence.some((row) => row.signal_id !== value.signal.signal_id)) context.addIssue({ code: "custom", path: ["evidence"], message: "Evidence identity must match signal" });
  if (value.signal.signal_type === "demand_momentum") {
    const historical = value.evidence.filter((row) => row.evidence_type === "historical_week" && row.path === null);
    const forward = value.evidence.filter((row) => row.evidence_type === "forward_demand" && row.path === "base");
    if (value.evidence.length !== 36 || historical.length !== 8 || forward.length !== 28) context.addIssue({ code: "custom", path: ["evidence"], message: "Demand evidence must contain eight historical weeks and 28 forward days" });
    return;
  }
  const counts = { low: 0, base: 0, high: 0 };
  for (const row of value.evidence) if (row.evidence_type === "inventory_projection" && row.path !== null) counts[row.path] += 1;
  if (value.evidence.length !== 84 || Object.values(counts).some((count) => count !== 28)) context.addIssue({ code: "custom", path: ["evidence"], message: "Inventory evidence must contain three complete paths" });
  if (value.signal.signal_type === "availability" && value.evidence.some((row) => row.target_units !== null)) context.addIssue({ code: "custom", path: ["evidence"], message: "Availability evidence cannot contain target units" });
  if (value.signal.signal_type === "inventory_imbalance" && value.evidence.some((row) => row.target_units === null)) context.addIssue({ code: "custom", path: ["evidence"], message: "Inventory imbalance evidence requires target units" });
});

export type SignalQueue = z.infer<typeof signalQueueSchema>;
export type SignalRow = z.infer<typeof signalSchema>;
export type SignalDetail = z.infer<typeof signalDetailSchema>;
export type SignalType = z.infer<typeof signalType>;
