from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from .metrics import ProjectionDay, clamp
from .metrics import project_inventory
from .signal_contract import CandidateBatch, Observation, common_signal_fields, decimal_value, stable_signal_id


@dataclass(frozen=True)
class InventoryImbalanceResult:
    eligible: bool
    reason_code: str | None
    safety_days: int
    target_cover_days: int
    target_units: float
    projected_excess_units: float
    inventory_cost_exposed: float
    carrying_cost_28d: float
    days_until_material_impact: int | None
    first_material_date: date | None
    path_stability: float


def calculate_inventory_imbalance(
    projection: Sequence[ProjectionDay],
    *,
    mean_base_daily_demand: float,
    minimum_reaction_days: int,
    forecast_wape: float,
    unit_cost_amount: float,
    annual_carrying_cost_rate: float,
) -> InventoryImbalanceResult:
    if mean_base_daily_demand < 0 or minimum_reaction_days < 0 or unit_cost_amount < 0:
        raise ValueError("inventory policy inputs must be nonnegative")
    if not 0 <= annual_carrying_cost_rate <= 1:
        raise ValueError("annual carrying cost rate must be between zero and one")
    paths = {name: sorted((row for row in projection if row.path == name), key=lambda row: row.date) for name in ("low", "base", "high")}
    if any(len(rows) != 28 for rows in paths.values()):
        raise ValueError("inventory imbalance requires three complete 28-day paths")
    safety_days = math.ceil(7 * clamp(forecast_wape, 0, 1))
    cover_days = minimum_reaction_days + safety_days
    target = mean_base_daily_demand * cover_days
    if any(row.lost_units > 0 for row in paths["base"]):
        return InventoryImbalanceResult(False, "inventory_imbalance_base_oos", safety_days, cover_days, target, 0, 0, 0, None, None, 0)
    excess = max(paths["base"][-1].ending_units - target, 0)
    if excess <= 0:
        return InventoryImbalanceResult(False, "inventory_imbalance_no_excess", safety_days, cover_days, target, 0, 0, 0, None, None, 0)

    def first_persistent(rows: Sequence[ProjectionDay]) -> int | None:
        for index, row in enumerate(rows):
            if row.ending_units > target and all(later.ending_units > target for later in rows[index:]):
                return index + 1
        return None

    timings = [first_persistent(paths[name]) for name in ("high", "base", "low")]
    base_day = timings[1]
    assert base_day is not None
    finite = [value for value in timings if value is not None]
    stability = 0.0 if len(finite) != 3 else 1 - clamp((max(finite) - min(finite)) / 28, 0, 1)
    cost = excess * unit_cost_amount
    carrying = cost * annual_carrying_cost_rate * 28 / 365
    first_date = paths["base"][base_day - 1].date
    return InventoryImbalanceResult(True, None, safety_days, cover_days, target, excess, cost, carrying, base_day, first_date, stability)


def build_inventory_candidate(
    observation: Observation, canonical_manifest: dict[str, object], *,
    forward_daily_forecast: Sequence[float], forecast_quality: float, history_count: int,
    minimum_reaction_days: int, inbound_by_date: dict[date, float], annual_carrying_cost_rate: float,
) -> CandidateBatch:
    """Produce at most one unranked Inventory Imbalance candidate and evidence."""
    band = 1 - forecast_quality
    paths: dict[str, Sequence[float]] = {name: [value * factor for value in forward_daily_forecast] for name, factor in (("low", 1-band), ("base", 1), ("high", 1+band))}
    horizon = [observation["observation_date"] + timedelta(days=index) for index in range(1, 29)]
    trace, _ = project_inventory(float(observation["on_hand"]), horizon, paths, inbound_by_date)
    result = calculate_inventory_imbalance(
        trace, mean_base_daily_demand=sum(forward_daily_forecast) / 28,
        minimum_reaction_days=minimum_reaction_days, forecast_wape=band,
        unit_cost_amount=float(observation["unit_cost"]), annual_carrying_cost_rate=annual_carrying_cost_rate,
    )
    if not result.eligible:
        return CandidateBatch(reason_codes=[result.reason_code] if result.reason_code else [])
    key = (str(observation["store_id"]), str(observation["product_id"]))
    signal_id = stable_signal_id(str(canonical_manifest["source_release_set_id"]), str(canonical_manifest["as_of"]), *key, "inventory_imbalance", str(result.first_material_date))
    common = common_signal_fields(
        observation, canonical_manifest, signal_id, "inventory_imbalance", "excess", "projected_excess_units",
        result.projected_excess_units, result.days_until_material_impact or 28, minimum_reaction_days,
        forecast_quality, min(history_count / 8, 1), result.path_stability,
    )
    primary = result.inventory_cost_exposed + result.carrying_cost_28d
    candidate = {
        **common, "estimated_retail_sales_impact_amount": None, "estimated_contribution_impact_amount": None,
        "estimated_cost_impact_amount": decimal_value(result.carrying_cost_28d, 2),
        "inventory_cost_exposed_amount": decimal_value(result.inventory_cost_exposed, 2),
        "carrying_cost_28d_amount": decimal_value(result.carrying_cost_28d, 2),
        "economic_impact_basis": "inventory_capital_plus_28d_carrying_cost_exposure",
        "primary_economic_value": decimal_value(primary, 2),
    }
    evidence = [{
        "signal_id": signal_id, "evidence_type": "inventory_projection", "evidence_date": item.date,
        "path": item.path, "actual_units": None, "retailer_forecast_units": None,
        "adjusted_forecast_units": None, "demand_units": decimal_value(item.demand_units, 6),
        "scheduled_inbound_units": decimal_value(item.inbound_units, 6), "opening_units": decimal_value(item.opening_units, 6),
        "ending_units": decimal_value(item.ending_units, 6), "lost_units": decimal_value(item.lost_units, 6),
        "target_units": decimal_value(result.target_units, 6),
    } for item in trace]
    return CandidateBatch([candidate], evidence)
