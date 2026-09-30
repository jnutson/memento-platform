from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence


HORIZON_DAYS = 28


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def bias_factor(actual_forecast_pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(actual_forecast_pairs) < 6:
        return None
    actual = sum(pair[0] for pair in actual_forecast_pairs)
    forecast = sum(pair[1] for pair in actual_forecast_pairs)
    if forecast <= 0:
        return None
    return clamp(actual / forecast, 0.5, 1.5)


def forecast_wape(actual_forecast_pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(actual_forecast_pairs) < 6:
        return None
    denominator = sum(actual for actual, _ in actual_forecast_pairs)
    if denominator <= 0:
        return None
    return sum(abs(actual - forecast) for actual, forecast in actual_forecast_pairs) / denominator


def normalize_weekday_shares(units: Sequence[float]) -> tuple[float, ...]:
    if len(units) != 7:
        raise ValueError("weekday shares require seven values")
    if any(value < 0 or not math.isfinite(value) for value in units):
        raise ValueError("weekday units must be finite and nonnegative")
    total = sum(units)
    if total <= 0:
        return (1 / 7,) * 7
    shares = [value / total for value in units]
    shares[-1] = 1.0 - sum(shares[:-1])
    return tuple(shares)


def demand_paths(base: float, error_band: float) -> dict[str, float]:
    if base < 0 or not math.isfinite(base):
        raise ValueError("base demand must be finite and nonnegative")
    band = clamp(error_band, 0, 1)
    return {"low": max(base * (1 - band), 0), "base": base, "high": base * (1 + band)}


@dataclass(frozen=True)
class ProjectionDay:
    date: date
    path: str
    demand_units: float
    inbound_units: float
    opening_units: float
    available_units: float
    fulfilled_units: float
    lost_units: float
    ending_units: float


def project_inventory(
    starting_on_hand: float,
    dates: Sequence[date],
    demand: dict[str, Sequence[float]],
    inbound: dict[date, float],
) -> tuple[list[ProjectionDay], dict[str, date | None]]:
    if starting_on_hand < 0:
        raise ValueError("starting inventory cannot be negative")
    if len(dates) != HORIZON_DAYS or any(len(demand[path]) != len(dates) for path in ("low", "base", "high")):
        raise ValueError("projection requires three 28-day demand paths")
    rows: list[ProjectionDay] = []
    oos: dict[str, date | None] = {"low": None, "base": None, "high": None}
    for path in ("low", "base", "high"):
        ending = float(starting_on_hand)
        for day, demand_units in zip(dates, demand[path], strict=True):
            opening = ending
            added = float(inbound.get(day, 0))
            if demand_units < 0 or added < 0:
                raise ValueError("demand and inbound must be nonnegative")
            available = opening + added
            fulfilled = min(available, demand_units)
            lost = max(demand_units - available, 0)
            ending = max(available - demand_units, 0)
            rows.append(ProjectionDay(day, path, demand_units, added, opening, available, fulfilled, lost, ending))
            if ending == 0 and oos[path] is None:
                oos[path] = day
    return rows, oos


def impact_scores(amounts: Sequence[float]) -> list[float]:
    if not amounts:
        return []
    if len(amounts) == 1:
        return [1.0]
    logged = [math.log1p(value) for value in amounts]
    ordered = sorted((value, index) for index, value in enumerate(logged))
    scores = [0.0] * len(amounts)
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][0] == ordered[position][0]:
            end += 1
        average_rank = ((position + 1) + end) / 2
        score = (average_rank - 1) / (len(amounts) - 1)
        for _, original in ordered[position:end]:
            scores[original] = score
        position = end
    return scores


def reaction_metrics(days_until_oos: int, minimum_reaction_days: int) -> tuple[int, float]:
    slack = days_until_oos - minimum_reaction_days
    urgency = 1 - clamp(days_until_oos / HORIZON_DAYS, 0, 1)
    return slack, urgency * (1.0 if slack >= 0 else 0.25)


def data_completeness(
    valid_sales_days: int,
    expected_sales_days: int,
    valid_inventory_days: int,
    expected_inventory_days: int,
    eligible_pairs: int,
    inbound_reconciliation_rate: float,
) -> float:
    if expected_sales_days <= 0 or expected_inventory_days <= 0:
        raise ValueError("expected coverage days must be positive")
    sales = clamp(valid_sales_days / expected_sales_days, 0, 1)
    inventory = clamp(valid_inventory_days / expected_inventory_days, 0, 1)
    pair_coverage = clamp(eligible_pairs / 6, 0, 1)
    inbound = 1 - clamp(inbound_reconciliation_rate, 0, 1)
    return 0.30 * sales + 0.30 * inventory + 0.25 * pair_coverage + 0.15 * inbound


def timing_stability(earliest: date | None, base: date | None, latest: date | None) -> tuple[int | None, float | None]:
    if base is None:
        return None, None
    if earliest is None or latest is None:
        return None, 0.0
    span = (latest - earliest).days
    return span, 1 - clamp(span / HORIZON_DAYS, 0, 1)


def confidence_score(wape: float | None, completeness: float, stability: float) -> tuple[float, float]:
    quality = 1 - clamp(wape, 0, 1) if wape is not None else 0.0
    return quality, 0.50 * quality + 0.30 * completeness + 0.20 * stability


def stable_prediction_id(
    source_release_set_id: str, prediction_as_of: str, location_id: str, product_id: str, predicted_oos_date: date
) -> str:
    preimage = "|".join((source_release_set_id, prediction_as_of, location_id, product_id, predicted_oos_date.isoformat()))
    return "oos_" + hashlib.sha256(preimage.encode()).hexdigest()


def rank_score(impact: float, reaction: float, confidence: float) -> float:
    return 0.50 * impact + 0.30 * reaction + 0.20 * confidence
