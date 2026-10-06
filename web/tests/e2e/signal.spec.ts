import { expect, test } from "@playwright/test";

const types = ["availability", "demand_momentum", "inventory_imbalance"] as const;
const ids = types.map((_, index) => `sig_${String(index + 1).repeat(64)}`);
const base = {
  observation_date: "2027-01-29", store_id: "loc_test", product_id: "prd_test",
  identity: { item_name: "Miro Spark One", company_item_id: "MIRO-SPARK-001", source_product_id: "100", store_name: "Synthetic Store 10", source_location_id: "10" },
  headline_metric_name: "units", headline_metric_value: "12.000000", minimum_reaction_days: 10,
  action_slack_days: 2, impact_score: "1.000000", reaction_score: "0.500000", confidence_score: "0.800000", rank_score: "0.810000",
};
const signals = types.map((signal_type, index) => ({
  ...base, signal_id: ids[index], signal_type, signal_direction: signal_type === "availability" ? "risk" : signal_type === "demand_momentum" ? "acceleration" : "excess",
  estimated_retail_sales_impact_amount: signal_type === "inventory_imbalance" ? null : "120.00",
  estimated_contribution_impact_amount: signal_type === "inventory_imbalance" ? null : "60.00",
  estimated_cost_impact_amount: signal_type === "inventory_imbalance" ? "2.00" : null,
  inventory_cost_exposed_amount: signal_type === "inventory_imbalance" ? "100.00" : null,
  carrying_cost_28d_amount: signal_type === "inventory_imbalance" ? "2.00" : null,
  economic_impact_basis: signal_type === "inventory_imbalance" ? "inventory_capital_plus_28d_carrying_cost_exposure" : "estimated_lost_retail_sales",
  days_until_material_impact: index + 2, overall_rank_position: index + 1, signal_type_rank_position: 1,
}));
const run = { signal_set_id: `mss_${"a".repeat(64)}`, signal_as_of: "2027-01-30T12:00:00Z", candidate_count: 3, display_count: 3, candidate_counts_by_type: { availability: 1, demand_momentum: 1, inventory_imbalance: 1 }, canonical_dataset_id: "mds_fixture", source_release_set_id: "fixture-release", source_release_ids: ["fixture-walmart", "fixture-extension"], metric_contract_version: "memento-signal-metrics-v1.0.0", signal_publication_version: "memento-signal-publication-v1", ranker_version: "memento-signal-ranker-v1", configuration_hash: "c".repeat(64) };
const day = (offset: number) => new Date(Date.UTC(2027, 0, 29 + offset)).toISOString().slice(0, 10);
const evidenceFor = (signal: typeof signals[number]) => signal.signal_type === "demand_momentum"
  ? [
      ...Array.from({ length: 8 }, (_, index) => ({ signal_id: signal.signal_id, evidence_type: "historical_week", evidence_date: day(-56 + index * 7), path: null, actual_units: "10.000000", retailer_forecast_units: "8.000000", adjusted_forecast_units: null, demand_units: null, scheduled_inbound_units: null, opening_units: null, ending_units: null, lost_units: null, target_units: null })),
      ...Array.from({ length: 28 }, (_, index) => ({ signal_id: signal.signal_id, evidence_type: "forward_demand", evidence_date: day(index + 1), path: "base", actual_units: null, retailer_forecast_units: "8.000000", adjusted_forecast_units: "10.000000", demand_units: null, scheduled_inbound_units: null, opening_units: null, ending_units: null, lost_units: null, target_units: null })),
    ]
  : (["low", "base", "high"] as const).flatMap((path) => Array.from({ length: 28 }, (_, index) => ({ signal_id: signal.signal_id, evidence_type: "inventory_projection", evidence_date: day(index + 1), path, actual_units: null, retailer_forecast_units: null, adjusted_forecast_units: null, demand_units: "1.000000", scheduled_inbound_units: "0.000000", opening_units: "20.000000", ending_units: "19.000000", lost_units: "0.000000", target_units: signal.signal_type === "inventory_imbalance" ? "12.000000" : null })));

test("filters and inspects all three signal types without renumbering", async ({ page }) => {
  await page.route("**/api/signals**", async (route) => {
    const url = new URL(route.request().url());
    const id = url.pathname.split("/").at(-1);
    if (id?.startsWith("sig_")) {
      const signal = signals.find((row) => row.signal_id === id)!;
      await route.fulfill({ json: { api_contract_version: "memento-signal-api-v1", signal: { ...signal, signal_as_of: run.signal_as_of, company_id: "MIRO_TOYS", brand_id: "MIRO_SPARK", forecast_quality: "0.800000", data_completeness: "1.000000", stability_score: "1.000000", source_release_ids: run.source_release_ids, source_release_set_id: run.source_release_set_id, canonical_dataset_id: run.canonical_dataset_id, metric_contract_version: run.metric_contract_version, signal_publication_version: run.signal_publication_version, ranker_version: run.ranker_version, configuration_hash: run.configuration_hash }, evidence: evidenceFor(signal) } });
      return;
    }
    const filter = url.searchParams.get("signal_type");
    await route.fulfill({ json: { api_contract_version: "memento-signal-api-v1", run, signals: filter ? signals.filter((row) => row.signal_type === filter) : signals } });
  });
  await page.goto("/signal");
  await expect(page.getByRole("heading", { name: "Memento Signal" })).toBeVisible();
  for (let index = 0; index < types.length; index += 1) {
    const label = ["Availability Risk", "Demand Momentum Gap", "Inventory Imbalance Exposure"][index];
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByRole("button", { name: new RegExp(`#${index + 1} · ${label}`) })).toBeVisible();
    await page.getByRole("button", { name: new RegExp(`#${index + 1} · ${label}`) }).click();
    await expect(page.getByText("Confidence is an evidence-quality score, not a probability.")).toBeVisible();
  }
});
