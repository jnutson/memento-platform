from datetime import date, timedelta

import pytest

from memento.metrics import (
    bias_factor, confidence_score, data_completeness, demand_paths, forecast_wape,
    impact_scores, normalize_weekday_shares, project_inventory, reaction_metrics,
    timing_stability,
)


def test_forecast_math_and_fallback_band_are_hand_calculable():
    pairs = [(10.0, 8.0)] * 6
    assert bias_factor(pairs) == 1.25
    assert forecast_wape([(10.0, 9.0)] * 6) == pytest.approx(0.1)
    assert demand_paths(10, 0.2) == {"low": 8, "base": 10, "high": 12}
    assert sum(normalize_weekday_shares([1] * 7)) == 1


def test_inventory_adds_dated_inbound_once_and_orders_oos_paths():
    start = date(2027, 1, 30)
    days = [start + timedelta(days=i) for i in range(28)]
    demand = {"low": [1.0] * 28, "base": [2.0] * 28, "high": [3.0] * 28}
    rows, oos = project_inventory(4, days, demand, {days[1]: 2})
    assert sum(row.inbound_units for row in rows if row.path == "base") == 2
    assert oos["high"] <= oos["base"] <= oos["low"]


def test_scores_follow_contract_equations_and_average_ties():
    assert impact_scores([10, 10, 100]) == pytest.approx([0.25, 0.25, 1.0])
    slack, reaction = reaction_metrics(7, 10)
    assert slack == -3 and reaction == pytest.approx(0.1875)
    completeness = data_completeness(56, 56, 56, 56, 6, 0.1)
    assert completeness == pytest.approx(0.985)
    span, stability = timing_stability(date(2027, 2, 1), date(2027, 2, 3), date(2027, 2, 8))
    assert span == 7 and stability == pytest.approx(0.75)
    quality, confidence = confidence_score(0.2, 0.9, 0.75)
    assert quality == pytest.approx(0.8)
    assert confidence == pytest.approx(0.82)
