from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from .metrics import clamp, forecast_wape
from .signal_contract import CandidateBatch, Observation, common_signal_fields, decimal_value, stable_signal_id


MULTIPLIER_MIN = 0.50
MULTIPLIER_MAX = 1.50


@dataclass(frozen=True)
class DemandMomentumResult:
    eligible: bool
    reason_code: str | None
    direction: str | None
    baseline_ratio: float | None
    recent_ratio: float | None
    momentum_multiplier: float | None
    forecast_gap_units: float
    error_band_units: float
    days_until_material_impact: int | None
    forecast_quality: float
    directional_persistence: float


def calculate_demand_momentum(
    weekly_pairs: Sequence[tuple[float, float]],
    forward_daily_forecast: Sequence[float],
) -> DemandMomentumResult:
    """Calculate the contracted eight-week, stockout-aware momentum gap.

    Callers must censor invalid, negative-sales, and observed-OOS weeks before
    invoking this pure boundary. Exactly eight completed weekly pairs and 28
    nonnegative daily forecast values are required for an eligible result.
    """
    if len(weekly_pairs) != 8:
        return DemandMomentumResult(False, "demand_momentum_missing_history", None, None, None, None, 0, 0, None, 0, 0)
    if len(forward_daily_forecast) != 28 or any(value < 0 for value in forward_daily_forecast):
        raise ValueError("demand momentum requires 28 nonnegative forward values")
    if any(actual < 0 or forecast <= 0 for actual, forecast in weekly_pairs):
        return DemandMomentumResult(False, "demand_momentum_invalid_history", None, None, None, None, 0, 0, None, 0, 0)
    prior = weekly_pairs[:6]
    recent = weekly_pairs[6:]
    prior_actual = sum(value[0] for value in prior)
    prior_forecast = sum(value[1] for value in prior)
    if prior_forecast <= 0:
        return DemandMomentumResult(False, "demand_momentum_missing_history", None, None, None, None, 0, 0, None, 0, 0)
    baseline = prior_actual / prior_forecast
    if baseline <= 0:
        return DemandMomentumResult(False, "demand_momentum_zero_baseline", None, baseline, None, None, 0, 0, None, 0, 0)
    recent_ratios = [actual / forecast for actual, forecast in recent]
    signs = [1 if ratio > baseline else -1 if ratio < baseline else 0 for ratio in recent_ratios]
    if signs[0] == 0 or signs[0] != signs[1]:
        wape = forecast_wape(prior)
        return DemandMomentumResult(False, "demand_momentum_not_persistent", None, baseline, sum(recent_ratios) / 2, None, 0, 0, None, 1 - clamp(wape if wape is not None else 1, 0, 1), 0)
    recent_ratio = sum(value[0] for value in recent) / sum(value[1] for value in recent)
    raw_multiplier = recent_ratio / baseline
    multiplier = clamp(raw_multiplier, MULTIPLIER_MIN, MULTIPLIER_MAX)
    total_forward = sum(forward_daily_forecast)
    gap = total_forward * (multiplier - 1)
    wape = forecast_wape(prior)
    error_units = total_forward * clamp(wape if wape is not None else 1, 0, 1)
    quality = 1 - clamp(wape if wape is not None else 1, 0, 1)
    if abs(gap) <= error_units:
        return DemandMomentumResult(False, "demand_momentum_within_error_band", None, baseline, recent_ratio, multiplier, gap, error_units, None, quality, 1)
    threshold = abs(gap) / 2
    cumulative = 0.0
    material_day = 28
    for index, value in enumerate(forward_daily_forecast, 1):
        cumulative += abs(value * (multiplier - 1))
        if cumulative + 1e-12 >= threshold:
            material_day = index
            break
    direction = "acceleration" if gap > 0 else "deceleration"
    return DemandMomentumResult(True, None, direction, baseline, recent_ratio, multiplier, gap, error_units, material_day, quality, 1)


def build_demand_candidate(
    observation: Observation, canonical_manifest: dict[str, object], *,
    weekly_history: Sequence[tuple[int, float, float]], forward_daily_forecast: Sequence[float],
    minimum_reaction_days: int,
) -> CandidateBatch:
    """Produce at most one unranked Demand Momentum candidate and its evidence."""
    result = calculate_demand_momentum([(row[1], row[2]) for row in weekly_history], forward_daily_forecast)
    if not result.eligible:
        return CandidateBatch(reason_codes=[result.reason_code] if result.reason_code else [])
    price = observation["price"]
    if price is None:
        raise ValueError("demand candidate requires an applicable unit price")
    key = (str(observation["store_id"]), str(observation["product_id"]))
    signal_id = stable_signal_id(str(canonical_manifest["source_release_set_id"]), str(canonical_manifest["as_of"]), *key, "demand_momentum", result.direction or "")
    completeness = min(len(weekly_history) / 8, 1)
    common = common_signal_fields(
        observation, canonical_manifest, signal_id, "demand_momentum", result.direction or "acceleration",
        "forecast_gap_units", abs(result.forecast_gap_units), result.days_until_material_impact or 28,
        minimum_reaction_days, result.forecast_quality, completeness, result.directional_persistence,
    )
    retail = abs(result.forecast_gap_units) * price
    contribution = abs(result.forecast_gap_units) * max(price - observation["unit_cost"], 0)
    candidate = {
        **common, "estimated_retail_sales_impact_amount": decimal_value(retail, 2),
        "estimated_contribution_impact_amount": decimal_value(contribution, 2), "estimated_cost_impact_amount": None,
        "inventory_cost_exposed_amount": None, "carrying_cost_28d_amount": None,
        "economic_impact_basis": "forward_contribution_opportunity" if result.direction == "acceleration" else "forecast_overstatement_contribution_exposure",
        "primary_economic_value": decimal_value(contribution, 2),
    }
    evidence = []
    for index, (_, actual, retailer) in enumerate(weekly_history):
        evidence.append({
            "signal_id": signal_id, "evidence_type": "historical_week",
            "evidence_date": observation["observation_date"] - timedelta(days=(8-index)*7), "path": None,
            "actual_units": decimal_value(actual, 6), "retailer_forecast_units": decimal_value(retailer, 6),
            "adjusted_forecast_units": None, "demand_units": None, "scheduled_inbound_units": None,
            "opening_units": None, "ending_units": None, "lost_units": None, "target_units": None,
        })
    for index, base in enumerate(forward_daily_forecast, 1):
        evidence.append({
            "signal_id": signal_id, "evidence_type": "forward_demand",
            "evidence_date": observation["observation_date"] + timedelta(days=index), "path": "base",
            "actual_units": None, "retailer_forecast_units": decimal_value(base, 6),
            "adjusted_forecast_units": decimal_value(base * (result.momentum_multiplier or 1), 6),
            "demand_units": None, "scheduled_inbound_units": None, "opening_units": None,
            "ending_units": None, "lost_units": None, "target_units": None,
        })
    return CandidateBatch([candidate], evidence)
