from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .signal_contract import CandidateBatch, common_signal_fields, decimal_value, stable_signal_id


def build_availability_candidates(
    connection: duckdb.DuckDBPyConnection,
    *,
    prediction_root: Path,
    observations: list[dict[str, object]],
    canonical_manifest: dict[str, object],
) -> CandidateBatch:
    """Adapt immutable legacy OOS outputs into unranked Availability signals."""
    batch = CandidateBatch()
    prediction_manifest = json.loads((prediction_root / "manifest.json").read_text(encoding="utf-8"))
    for code, count in prediction_manifest.get("reason_code_counts", {}).items():
        batch.reason_codes.extend([str(code)] * int(count))
    observation_by_key = {(row["store_id"], row["product_id"]): row for row in observations}
    predictions = connection.execute(
        "SELECT * FROM read_parquet(?)", [str(prediction_root / "oos_prediction.parquet")]
    ).to_arrow_table().to_pylist()
    for source in predictions:
        observation = observation_by_key[(source["store_id"], source["product_id"])]
        signal_id = stable_signal_id(
            str(canonical_manifest["source_release_set_id"]), str(canonical_manifest["as_of"]),
            str(source["store_id"]), str(source["product_id"]), "availability", str(source["predicted_oos_date"]),
        )
        common = common_signal_fields(
            {**observation, "observation_date": source["prediction_date"]}, canonical_manifest,
            signal_id, "availability", "risk", "estimated_lost_units", float(source["estimated_lost_units"]),
            int(source["days_until_predicted_oos"]), int(source["minimum_reaction_days"]),
            float(source["forecast_quality"]), float(source["data_completeness"]), float(source["timing_stability_score"]),
        )
        contribution = float(source["estimated_lost_units"]) * max(float(observation["price"]) - float(observation["unit_cost"]), 0)
        batch.candidates.append({
            **common, "estimated_retail_sales_impact_amount": source["estimated_lost_sales_amount"],
            "estimated_contribution_impact_amount": decimal_value(contribution, 2), "estimated_cost_impact_amount": None,
            "inventory_cost_exposed_amount": None, "carrying_cost_28d_amount": None,
            "economic_impact_basis": "estimated_lost_retail_sales", "primary_economic_value": source["estimated_lost_sales_amount"],
        })
        rows = connection.execute(
            "SELECT * FROM read_parquet(?) WHERE prediction_id=?",
            [str(prediction_root / "oos_prediction_evidence.parquet"), source["prediction_id"]],
        ).to_arrow_table().to_pylist()
        for item in rows:
            batch.evidence.append({
                "signal_id": signal_id, "evidence_type": "inventory_projection", "evidence_date": item["projection_date"],
                "path": item["path"], "actual_units": None, "retailer_forecast_units": None,
                "adjusted_forecast_units": None, "demand_units": item["demand_units"],
                "scheduled_inbound_units": item["scheduled_inbound_units"], "opening_units": item["opening_units"],
                "ending_units": item["projected_ending_on_hand_units"], "lost_units": item["lost_units"], "target_units": None,
            })
    return batch
