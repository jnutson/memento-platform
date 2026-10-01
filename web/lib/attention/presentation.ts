import type { AttentionDetail, AttentionPrediction } from "./schema";

export function displayNumber(value: string, maximumFractionDigits = 0): string {
  return Number(value).toLocaleString("en-US", { maximumFractionDigits });
}

export function displayMoney(value: string): string {
  return Number(value).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export function displayDate(value: string | null): string {
  if (!value) return "Not within horizon";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function scorePercent(value: string): number {
  return Number(value) * 100;
}

export function scoreLabel(value: string): string {
  return scorePercent(value).toFixed(0);
}

export function toWorld(prediction: AttentionPrediction): [number, number, number] {
  return [
    scorePercent(prediction.prediction_confidence_score) / 50 - 1,
    scorePercent(prediction.impact_score) / 50 - 1,
    scorePercent(prediction.reaction_score) / 50 - 1,
  ];
}

export function deterministicExplanation(detail: AttentionDetail): string {
  const prediction = detail.prediction;
  const range = prediction.earliest_oos_date || prediction.latest_oos_date
    ? ` Sensitivity paths place depletion between ${displayDate(prediction.earliest_oos_date)} and ${displayDate(prediction.latest_oos_date)}.`
    : " The sensitivity paths do not add a bounded depletion range.";
  const inbound = detail.scheduled_inbound.length
    ? ` Scheduled inbound includes ${detail.scheduled_inbound.map((row) => `${displayNumber(row.scheduled_inbound_units)} units on ${displayDate(row.expected_store_receipt_date)}`).join(", ")}.`
    : " No scheduled inbound is present in the 28-day evidence trace.";
  const slack = prediction.action_slack_days >= 0
    ? `${prediction.action_slack_days} days remain after the minimum reaction window.`
    : `The prediction is ${Math.abs(prediction.action_slack_days)} days inside the minimum reaction window.`;
  const components = [
    ["forecast quality", Number(prediction.forecast_quality)],
    ["data completeness", Number(prediction.data_completeness)],
    ["timing stability", Number(prediction.timing_stability_score)],
  ] as const;
  const limiting = [...components].sort((a, b) => a[1] - b[1])[0][0];
  return `The base path depletes on ${displayDate(prediction.predicted_oos_date)}, with an estimated ${displayNumber(prediction.estimated_lost_units)} lost units (${displayMoney(prediction.estimated_lost_sales_amount)}) over 28 days.${range}${inbound} ${slack} The lowest confidence component is ${limiting}.`;
}
