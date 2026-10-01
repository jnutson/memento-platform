import { z } from "zod";

export const API_CONTRACT_VERSION = "memento-attention-api-v1" as const;

const decimalPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;
export const decimalStringSchema = z.string().regex(decimalPattern, "Expected a fixed-point decimal string");
export const nonNegativeDecimalStringSchema = decimalStringSchema.refine((value) => Number(value) >= 0, "Expected a non-negative decimal");
export const scoreStringSchema = decimalStringSchema.refine((value) => {
  const score = Number(value);
  return Number.isFinite(score) && score >= 0 && score <= 1;
}, "Expected a score between 0 and 1");
export const dateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Expected YYYY-MM-DD");
export const utcTimestampSchema = z.iso.datetime({ offset: true });

const identitySchema = z.strictObject({
  item_name: z.string().min(1),
  company_item_id: z.string().min(1),
  source_product_id: z.string().min(1),
  store_name: z.string().min(1),
  source_location_id: z.string().min(1),
});

export const attentionPredictionSchema = z.strictObject({
  prediction_id: z.string().regex(/^oos_[0-9a-f]{64}$/),
  rank_position: z.number().int().min(1).max(10),
  store_id: z.string().min(1),
  product_id: z.string().min(1),
  identity: identitySchema,
  predicted_oos_date: dateSchema,
  estimated_lost_units: nonNegativeDecimalStringSchema,
  estimated_lost_sales_amount: nonNegativeDecimalStringSchema,
  impact_score: scoreStringSchema,
  reaction_score: scoreStringSchema,
  prediction_confidence_score: scoreStringSchema,
  rank_score: scoreStringSchema,
});

export const runMetadataSchema = z.strictObject({
  prediction_set_id: z.string().min(1),
  prediction_as_of: utcTimestampSchema,
  prediction_date: dateSchema,
  candidate_count: z.number().int().nonnegative(),
  display_count: z.number().int().min(0).max(10),
  canonical_dataset_id: z.string().min(1),
  source_release_set_id: z.string().min(1),
  source_release_ids: z.array(z.string().min(1)),
  metric_contract_version: z.string().min(1),
  demand_forecast_version: z.string().min(1),
  inventory_projection_version: z.string().min(1),
  ranker_version: z.string().min(1),
  configuration_hash: z.string().min(1),
});

export const attentionQueueSchema = z.strictObject({
  api_contract_version: z.literal(API_CONTRACT_VERSION),
  run: runMetadataSchema,
  summary: z.strictObject({
    eligible_candidate_count: z.number().int().nonnegative(),
    displayed_prediction_count: z.number().int().min(0).max(10),
    estimated_lost_units: nonNegativeDecimalStringSchema,
    estimated_lost_sales_amount: nonNegativeDecimalStringSchema,
  }),
  predictions: z.array(attentionPredictionSchema).max(10),
}).superRefine((value, context) => {
  if (value.summary.displayed_prediction_count !== value.predictions.length) {
    context.addIssue({ code: "custom", path: ["summary", "displayed_prediction_count"], message: "Display count must match predictions" });
  }
  for (let index = 0; index < value.predictions.length; index += 1) {
    if (value.predictions[index].rank_position !== index + 1) {
      context.addIssue({ code: "custom", path: ["predictions", index, "rank_position"], message: "Predictions must retain contiguous engine rank order" });
    }
  }
});

const detailPredictionSchema = attentionPredictionSchema.extend({
  prediction_as_of: utcTimestampSchema,
  prediction_date: dateSchema,
  company_id: z.string().min(1),
  brand_id: z.string().min(1),
  earliest_oos_date: dateSchema.nullable(),
  latest_oos_date: dateSchema.nullable(),
  days_until_predicted_oos: z.number().int(),
  minimum_reaction_days: z.number().int().nonnegative(),
  action_slack_days: z.number().int(),
  forecast_wape: nonNegativeDecimalStringSchema.nullable(),
  forecast_error_band: nonNegativeDecimalStringSchema,
  forecast_quality: scoreStringSchema,
  data_completeness: scoreStringSchema,
  oos_date_span_days: z.number().int().nonnegative().nullable(),
  timing_stability_score: scoreStringSchema,
  source_release_ids: z.array(z.string().min(1)),
  source_release_set_id: z.string().min(1),
  metric_contract_version: z.string().min(1),
  demand_forecast_version: z.string().min(1),
  inventory_projection_version: z.string().min(1),
  ranker_version: z.string().min(1),
  configuration_hash: z.string().min(1),
  starting_on_hand_units: nonNegativeDecimalStringSchema,
});

export const evidenceRowSchema = z.strictObject({
  prediction_id: z.string().regex(/^oos_[0-9a-f]{64}$/),
  projection_date: dateSchema,
  path: z.enum(["low", "base", "high"]),
  demand_units: nonNegativeDecimalStringSchema,
  scheduled_inbound_units: nonNegativeDecimalStringSchema,
  opening_units: nonNegativeDecimalStringSchema,
  available_units: nonNegativeDecimalStringSchema,
  fulfilled_units: nonNegativeDecimalStringSchema,
  lost_units: nonNegativeDecimalStringSchema,
  projected_ending_on_hand_units: nonNegativeDecimalStringSchema,
});

export const attentionDetailSchema = z.strictObject({
  api_contract_version: z.literal(API_CONTRACT_VERSION),
  prediction: detailPredictionSchema,
  evidence: z.array(evidenceRowSchema).length(84),
  scheduled_inbound: z.array(z.strictObject({
    expected_store_receipt_date: dateSchema,
    scheduled_inbound_units: nonNegativeDecimalStringSchema,
  })),
}).superRefine((value, context) => {
  const counts = { low: 0, base: 0, high: 0 };
  for (const row of value.evidence) counts[row.path] += 1;
  for (const path of ["low", "base", "high"] as const) {
    if (counts[path] !== 28) context.addIssue({ code: "custom", path: ["evidence"], message: `${path} path must contain 28 rows` });
  }
  if (value.prediction.prediction_id !== value.evidence[0]?.prediction_id) {
    context.addIssue({ code: "custom", path: ["evidence"], message: "Evidence identity mismatch" });
  }
});

export const apiErrorSchema = z.strictObject({
  api_contract_version: z.literal(API_CONTRACT_VERSION),
  code: z.string().min(1),
  message: z.string().min(1),
});

export type AttentionQueue = z.infer<typeof attentionQueueSchema>;
export type AttentionPrediction = z.infer<typeof attentionPredictionSchema>;
export type AttentionDetail = z.infer<typeof attentionDetailSchema>;
export type EvidenceRow = z.infer<typeof evidenceRowSchema>;
