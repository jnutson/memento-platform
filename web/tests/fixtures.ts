import type { AttentionDetail, AttentionQueue } from "@/lib/attention/schema";

export const predictionId = `oos_${"a".repeat(64)}`;

export const queueFixture: AttentionQueue = {
  api_contract_version: "memento-attention-api-v1",
  run: {
    prediction_set_id: `mps_${"b".repeat(64)}`,
    prediction_as_of: "2027-01-30T12:00:00Z",
    prediction_date: "2027-01-29",
    candidate_count: 1,
    display_count: 1,
    canonical_dataset_id: "mds_fixture",
    source_release_set_id: "fixture-release-set",
    source_release_ids: ["fixture-walmart", "fixture-extension"],
    metric_contract_version: "miro-oos-metrics-v1.6.0",
    demand_forecast_version: "miro-interpretable-demand-v1",
    inventory_projection_version: "miro-deterministic-inventory-v1",
    ranker_version: "miro-oos-ranker-v1",
    configuration_hash: "c".repeat(64),
  },
  summary: {
    eligible_candidate_count: 1,
    displayed_prediction_count: 1,
    estimated_lost_units: "26.000000",
    estimated_lost_sales_amount: "260.00",
  },
  predictions: [{
    prediction_id: predictionId,
    rank_position: 1,
    store_id: "loc_test",
    product_id: "prd_test",
    identity: {
      item_name: "Miro Spark One",
      company_item_id: "MIRO-SPARK-001",
      source_product_id: "100",
      store_name: "Synthetic Store 10",
      source_location_id: "10",
    },
    predicted_oos_date: "2027-01-31",
    estimated_lost_units: "26.000000",
    estimated_lost_sales_amount: "260.00",
    impact_score: "1.000000",
    reaction_score: "0.650000",
    prediction_confidence_score: "0.820000",
    rank_score: "0.859000",
  }],
};

const day = (offset: number) => {
  const value = new Date(Date.UTC(2027, 0, 30 + offset));
  return value.toISOString().slice(0, 10);
};

export const detailFixture: AttentionDetail = {
  api_contract_version: "memento-attention-api-v1",
  prediction: {
    ...queueFixture.predictions[0],
    prediction_as_of: "2027-01-30T12:00:00Z",
    prediction_date: "2027-01-29",
    company_id: "MIRO_TOYS",
    brand_id: "MIRO_SPARK",
    earliest_oos_date: "2027-01-31",
    latest_oos_date: "2027-02-02",
    days_until_predicted_oos: 2,
    minimum_reaction_days: 10,
    action_slack_days: -8,
    forecast_wape: "0.200000",
    forecast_error_band: "0.200000",
    forecast_quality: "0.800000",
    data_completeness: "0.950000",
    oos_date_span_days: 2,
    timing_stability_score: "0.930000",
    source_release_ids: ["fixture-walmart", "fixture-extension"],
    source_release_set_id: "fixture-release-set",
    metric_contract_version: "miro-oos-metrics-v1.6.0",
    demand_forecast_version: "miro-interpretable-demand-v1",
    inventory_projection_version: "miro-deterministic-inventory-v1",
    ranker_version: "miro-oos-ranker-v1",
    configuration_hash: "c".repeat(64),
    starting_on_hand_units: "2.000000",
  },
  evidence: (["low", "base", "high"] as const).flatMap((path) => Array.from({ length: 28 }, (_, index) => {
    const demand = path === "low" ? .8 : path === "base" ? 1 : 1.2;
    const inbound = index === 5 ? 5 : 0;
    const opening = Math.max(0, 2 + (index > 5 ? 5 : 0) - index * demand);
    const ending = Math.max(0, opening + inbound - demand);
    return {
      prediction_id: predictionId,
      projection_date: day(index + 1),
      path,
      demand_units: demand.toFixed(6),
      scheduled_inbound_units: inbound.toFixed(6),
      opening_units: opening.toFixed(6),
      available_units: (opening + inbound).toFixed(6),
      fulfilled_units: Math.min(opening + inbound, demand).toFixed(6),
      lost_units: Math.max(0, demand - opening - inbound).toFixed(6),
      projected_ending_on_hand_units: ending.toFixed(6),
    };
  })),
  scheduled_inbound: [{ expected_store_receipt_date: day(6), scheduled_inbound_units: "5.000000" }],
};
