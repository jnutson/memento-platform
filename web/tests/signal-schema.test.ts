import { describe, expect, it } from "vitest";
import { signalDetailSchema } from "@/lib/signal/schema";

const signalId = `sig_${"a".repeat(64)}`;
const signal = {
  signal_id: signalId, signal_type: "availability", signal_direction: "risk", observation_date: "2027-01-29",
  store_id: "loc_test", product_id: "prd_test",
  identity: { item_name: "Synthetic Item", company_item_id: "ITEM-1", source_product_id: "100", store_name: "Synthetic Store", source_location_id: "10" },
  headline_metric_name: "estimated_lost_units", headline_metric_value: "10.000000",
  estimated_retail_sales_impact_amount: "100.00", estimated_contribution_impact_amount: "50.00",
  estimated_cost_impact_amount: null, inventory_cost_exposed_amount: null, carrying_cost_28d_amount: null,
  economic_impact_basis: "estimated_lost_retail_sales", days_until_material_impact: 3,
  minimum_reaction_days: 10, action_slack_days: -7, impact_score: "1.000000", reaction_score: "0.100000",
  confidence_score: "0.800000", rank_score: "0.690000", overall_rank_position: 1, signal_type_rank_position: 1,
  signal_as_of: "2027-01-30T12:00:00Z", company_id: "MIRO_TOYS", brand_id: "MIRO_SPARK",
  forecast_quality: "0.800000", data_completeness: "1.000000", stability_score: "1.000000",
  source_release_ids: ["fixture"], source_release_set_id: "fixture-set", canonical_dataset_id: "mds_fixture",
  metric_contract_version: "metrics-v1", signal_publication_version: "publication-v1", ranker_version: "ranker-v1", configuration_hash: "c".repeat(64),
} as const;
const day = (offset: number) => new Date(Date.UTC(2027, 0, 29 + offset)).toISOString().slice(0, 10);
const evidence = (["low", "base", "high"] as const).flatMap((path) => Array.from({ length: 28 }, (_, index) => ({
  signal_id: signalId, evidence_type: "inventory_projection", evidence_date: day(index + 1), path,
  actual_units: null, retailer_forecast_units: null, adjusted_forecast_units: null, demand_units: "1.000000",
  scheduled_inbound_units: "0.000000", opening_units: "10.000000", ending_units: "9.000000",
  lost_units: "0.000000", target_units: null,
})));

describe("Memento Signal runtime contract", () => {
  it("accepts complete type-specific evidence", () => {
    expect(signalDetailSchema.safeParse({ api_contract_version: "memento-signal-api-v1", signal, evidence }).success).toBe(true);
  });

  it("rejects incomplete evidence and mismatched economics", () => {
    expect(signalDetailSchema.safeParse({ api_contract_version: "memento-signal-api-v1", signal, evidence: evidence.slice(1) }).success).toBe(false);
    expect(signalDetailSchema.safeParse({ api_contract_version: "memento-signal-api-v1", signal: { ...signal, inventory_cost_exposed_amount: "10.00" }, evidence }).success).toBe(false);
  });
});
