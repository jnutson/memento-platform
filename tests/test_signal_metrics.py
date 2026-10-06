from datetime import date, timedelta
from decimal import Decimal

import duckdb
import pytest

from memento.demand_signal import calculate_demand_momentum
from memento.inventory_signal import calculate_inventory_imbalance
from memento.metrics import project_inventory
from memento.models import IngestionFailure
from memento.signals import _daily_base_forecast, _load_observations, run_signals
from memento.signal_ranking import rank_signal_candidates
from test_prediction_pipeline import _canonical_fixture


def test_demand_momentum_acceleration_and_material_day():
    history = [(100, 100)] * 6 + [(130, 100), (140, 100)]
    result = calculate_demand_momentum(history, [10] * 28)
    assert result.eligible
    assert result.direction == "acceleration"
    assert result.momentum_multiplier == 1.35
    assert result.forecast_gap_units == pytest.approx(98)
    assert result.days_until_material_impact == 14


def test_demand_momentum_rejects_nonpersistent_and_error_band():
    assert calculate_demand_momentum([(100, 100)] * 6 + [(120, 100), (80, 100)], [10] * 28).reason_code == "demand_momentum_not_persistent"
    noisy = [(80, 100), (120, 100)] * 3 + [(110, 100), (110, 100)]
    assert calculate_demand_momentum(noisy, [10] * 28).reason_code == "demand_momentum_within_error_band"
    assert calculate_demand_momentum([(0, 100)] * 6 + [(10, 100), (10, 100)], [10] * 28).reason_code == "demand_momentum_zero_baseline"


def test_inventory_imbalance_equations_and_base_oos_exclusion():
    start = date(2027, 1, 1)
    days = [start + timedelta(days=index) for index in range(1, 29)]
    paths = {name: [1] * 28 for name in ("low", "base", "high")}
    trace, _ = project_inventory(100, days, paths, {})
    result = calculate_inventory_imbalance(trace, mean_base_daily_demand=1, minimum_reaction_days=10, forecast_wape=.2, unit_cost_amount=2, annual_carrying_cost_rate=.2)
    assert result.eligible
    assert result.safety_days == 2
    assert result.target_units == 12
    assert result.projected_excess_units == 60
    assert result.inventory_cost_exposed == 120
    assert result.carrying_cost_28d == pytest.approx(1.84109589)

    depleted, _ = project_inventory(1, days, paths, {})
    assert calculate_inventory_imbalance(depleted, mean_base_daily_demand=1, minimum_reaction_days=1, forecast_wape=0, unit_cost_amount=2, annual_carrying_cost_rate=.2).reason_code == "inventory_imbalance_base_oos"


def test_cross_type_ranking_normalizes_impact_within_type_and_keeps_fixed_order():
    candidates = []
    for signal_type, amount in (("inventory_imbalance", 10), ("availability", 10), ("demand_momentum", 10)):
        candidates.append({"signal_id": f"sig_{signal_type}", "signal_type": signal_type, "primary_economic_value": amount, "reaction_score": .5, "confidence_score": .5, "days_until_material_impact": 5, "store_id": "s", "product_id": "p"})
    ranked = rank_signal_candidates(candidates)
    assert [row["signal_type"] for row in ranked] == ["availability", "demand_momentum", "inventory_imbalance"]
    assert [row["overall_rank_position"] for row in ranked] == [1, 2, 3]
    assert all(row["impact_score"] == 1 for row in ranked)


def test_daily_base_forecast_uses_calendar_aligned_weekday_shares(tmp_path):
    canonical = _canonical_fixture(tmp_path)
    connection = duckdb.connect()
    observation = {"store_id": "loc_test", "product_id": "prd_test", "observation_date": date(2027, 1, 29)}
    weeks = connection.execute(
        "SELECT DISTINCT retail_year_week FROM read_parquet(?) WHERE calendar_date BETWEEN DATE '2027-01-30' AND DATE '2027-02-26'",
        [str(canonical / "calendar_day" / "*.parquet")],
    ).fetchall()
    future = [{"target_retail_year_week": week, "memento_weekly_demand_base": 7} for (week,) in weeks]
    weekday_inputs = ({("loc_test", "prd_test"): (4, [7, 0, 0, 0, 0, 0, 0])}, {}, (0, [0] * 7))

    daily = _daily_base_forecast(connection, canonical, observation, future, weekday_inputs)

    assert len(daily) == 28
    assert sum(daily) == 28
    assert sorted(set(daily)) == [0, 7]


def test_signal_observation_uses_realized_price_and_scoped_eligibility(tmp_path):
    canonical = _canonical_fixture(tmp_path)
    sales = canonical / "sales_daily" / "part-00000.parquet"
    replacement = canonical / "sales_daily" / "replacement.parquet"
    connection = duckdb.connect()
    connection.execute(
        "CREATE TEMP TABLE rewritten_sales AS SELECT * REPLACE "
        "(CASE WHEN business_date=DATE '2027-01-29' THEN 12.00 ELSE sales_amount END AS sales_amount) "
        "FROM read_parquet(?)",
        [str(sales)],
    )
    connection.execute("COPY rewritten_sales TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(replacement)])
    replacement.replace(sales)

    observations = _load_observations(connection, canonical)

    assert len(observations) == 1
    assert observations[0]["price"] == 12
    assert observations[0]["company_item_id"] == "MIRO-SPARK-001"


def test_signal_publication_adapts_availability_and_replays(tmp_path):
    (tmp_path / "source").mkdir()
    canonical = _canonical_fixture(tmp_path / "source")
    output = run_signals(canonical, data_root=tmp_path / "data", annual_carrying_cost_rate=Decimal("0.20"), carrying_rate_version="synthetic-test-rate-v1")
    import duckdb
    import json
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["candidate_counts_by_type"]["availability"] == 1
    assert manifest["reason_code_counts"] == {
        "demand_momentum_missing_history": 1,
        "inventory_imbalance_base_oos": 1,
    }
    row = duckdb.connect().execute("SELECT signal_type,estimated_retail_sales_impact_amount,estimated_contribution_impact_amount,overall_rank_position FROM read_parquet(?)", [str(output / "signal.parquet")]).fetchone()
    assert row == ("availability", 260, 156, 1)
    before = (output / "manifest.json").read_bytes()
    assert run_signals(canonical, data_root=tmp_path / "data", annual_carrying_cost_rate=Decimal("0.20"), carrying_rate_version="synthetic-test-rate-v1") == output
    assert (output / "manifest.json").read_bytes() == before


def test_signal_publication_rejects_incomplete_existing_manifest(tmp_path):
    (tmp_path / "source").mkdir()
    canonical = _canonical_fixture(tmp_path / "source")
    output = run_signals(canonical, data_root=tmp_path / "data", annual_carrying_cost_rate=Decimal("0.20"), carrying_rate_version="synthetic-test-rate-v1")
    import json
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = []
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    with pytest.raises(IngestionFailure, match="SIGNAL_IMMUTABLE_INTACT"):
        run_signals(canonical, data_root=tmp_path / "data", annual_carrying_cost_rate=Decimal("0.20"), carrying_rate_version="synthetic-test-rate-v1")
