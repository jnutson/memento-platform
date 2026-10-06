from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb

from .availability_signal import build_availability_candidates
from .demand_signal import build_demand_candidate
from .inventory_signal import build_inventory_candidate
from .models import IngestionFailure, ValidationResult
from .prediction import run_predictions
from .signal_contract import ForecastVintage, Observation, SIGNAL_TYPE_ORDER
from .signal_publication import publish_signal_set
from .signal_ranking import rank_signal_candidates
from .metrics import clamp, normalize_weekday_shares

__all__ = ["rank_signal_candidates", "run_signals"]


def _scan(canonical_root: Path, table: str) -> str:
    return str(canonical_root / table / "*.parquet")


def _load_observations(connection: duckdb.DuckDBPyConnection, canonical_root: Path) -> list[Observation]:
    rows = connection.execute("""WITH sales_day AS (
        SELECT business_date,location_id,product_id,sum(sales_quantity)::DOUBLE units,sum(sales_amount)::DOUBLE amount
        FROM read_parquet(?) GROUP BY ALL)
        SELECT i.business_date observation_date,i.location_id store_id,i.product_id,
        i.on_hand_quantity::DOUBLE on_hand,
        CASE WHEN s.units>0 THEN s.amount/s.units ELSE i.current_unit_retail_amount END::DOUBLE price,
        i.assorted,i.replenishment_enabled,l.source_status_code location_status,
        c.company_item_id,e.unit_cost_amount::DOUBLE unit_cost
        FROM read_parquet(?) i JOIN read_parquet(?) c USING(product_id)
        JOIN read_parquet(?) e USING(company_id,company_item_id)
        JOIN read_parquet(?) p USING(product_id) JOIN read_parquet(?) l USING(location_id)
        LEFT JOIN sales_day s USING(business_date,location_id,product_id)
        WHERE i.business_date=(SELECT max(business_date) FROM read_parquet(?))
          AND c.company_id='MIRO_TOYS' AND c.display_brand_id='MIRO_SPARK'
          AND p.brand_name='BRAND_A' AND upper(p.source_status_code) IN ('A','ACTIVE')
          AND p.effective_date<=i.business_date AND p.replenishment_enabled
          AND c.effective_from<=i.business_date AND (c.effective_to IS NULL OR c.effective_to>=i.business_date)
          AND e.effective_from<=i.business_date AND (e.effective_to IS NULL OR e.effective_to>=i.business_date)""", [
            _scan(canonical_root, "sales_daily"), _scan(canonical_root, "inventory_daily"),
            _scan(canonical_root, "company_item"), _scan(canonical_root, "company_item_economics"),
            _scan(canonical_root, "product"), _scan(canonical_root, "location"),
            _scan(canonical_root, "inventory_daily"),
        ]).fetchall()
    return [Observation(
        observation_date=row[0], store_id=str(row[1]), product_id=str(row[2]),
        on_hand=float(row[3]), price=float(row[4]) if row[4] is not None else None,
        assorted=bool(row[5]), replenishment_enabled=bool(row[6]), location_status=str(row[7]),
        company_item_id=str(row[8]), unit_cost=float(row[9]),
    ) for row in rows]


def _load_reactions(connection: duckdb.DuckDBPyConnection, canonical_root: Path, observation_date: date) -> dict[tuple[str, str], int]:
    rows = connection.execute("""SELECT item_scope_type_code,item_scope_id,minimum_reaction_days
        FROM read_parquet(?) WHERE company_id='MIRO_TOYS'
          AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)""", [
            _scan(canonical_root, "reaction_constraint"), observation_date, observation_date,
        ]).fetchall()
    return {(str(scope), str(key)): int(days) for scope, key, days in rows}


def _minimum_reaction(observation: Observation, reactions: dict[tuple[str, str], int]) -> int:
    value = reactions.get(("item", str(observation["company_item_id"])), reactions.get(("brand", "MIRO_SPARK"), reactions.get(("all", "all"))))
    if value is None:
        raise ValueError(f"no effective reaction constraint for product {observation['product_id']}")
    return value


def _load_history(connection: duckdb.DuckDBPyConnection, canonical_root: Path, observation: Observation) -> list[tuple[int, float, float]]:
    rows = connection.execute("""WITH weekly AS (
      SELECT c.retail_year_week,sum(s.sales_quantity)::DOUBLE actual_units
      FROM read_parquet(?) s JOIN read_parquet(?) i USING(business_date,location_id,product_id)
      JOIN read_parquet(?) c ON c.calendar_date=s.business_date
      WHERE s.location_id=? AND s.product_id=? AND s.business_date<? AND s.sales_quantity>=0
        AND NOT(i.on_hand_quantity=0 AND i.assorted AND i.replenishment_enabled)
      GROUP BY c.retail_year_week HAVING count(DISTINCT s.business_date)=7
    ), selected AS (
      SELECT w.retail_year_week,w.actual_units,f.forecast_quantity::DOUBLE forecast_units
      FROM weekly w JOIN read_parquet(?) f ON f.target_retail_year_week=w.retail_year_week
      WHERE f.location_id=? AND f.product_id=? AND f.forecast_created_retail_year_week<f.target_retail_year_week
      QUALIFY row_number() OVER(PARTITION BY w.retail_year_week ORDER BY f.forecast_created_retail_year_week DESC)=1)
    SELECT * FROM selected ORDER BY retail_year_week DESC LIMIT 8""", [
        _scan(canonical_root, "sales_daily"), _scan(canonical_root, "inventory_daily"), _scan(canonical_root, "calendar_day"),
        observation["store_id"], observation["product_id"], observation["observation_date"],
        _scan(canonical_root, "demand_forecast_weekly"), observation["store_id"], observation["product_id"],
    ]).fetchall()[::-1]
    return [(int(week), float(actual), float(forecast)) for week, actual, forecast in rows]


def _load_weekday_inputs(
    connection: duckdb.DuckDBPyConnection, canonical_root: Path, observation_date: date,
) -> tuple[
    dict[tuple[str, str], tuple[int, list[float]]],
    dict[str, tuple[int, list[float]]],
    tuple[int, list[float]],
]:
    history_start = observation_date - timedelta(days=55)
    rows = connection.execute("""WITH scoped AS (
      SELECT c.product_id FROM read_parquet(?) c JOIN read_parquet(?) p USING(product_id)
      WHERE c.company_id='MIRO_TOYS' AND c.display_brand_id='MIRO_SPARK' AND p.brand_name='BRAND_A'
        AND upper(p.source_status_code) IN ('A','ACTIVE') AND p.effective_date<=? AND p.replenishment_enabled
        AND c.effective_from<=? AND (c.effective_to IS NULL OR c.effective_to>=?)
    ), sales_day AS (
      SELECT business_date,location_id,product_id,sum(sales_quantity)::DOUBLE units
      FROM read_parquet(?) WHERE business_date BETWEEN ? AND ? GROUP BY ALL
    ), eligible_week AS (
      SELECT s.location_id,s.product_id,c.retail_year_week
      FROM sales_day s JOIN scoped q USING(product_id) JOIN read_parquet(?) i USING(business_date,location_id,product_id)
      JOIN read_parquet(?) c ON c.calendar_date=s.business_date
      WHERE s.units>=0 AND i.on_hand_quantity>=0 AND i.assorted AND i.replenishment_enabled
        AND NOT(i.on_hand_quantity=0 AND i.assorted AND i.replenishment_enabled)
      GROUP BY s.location_id,s.product_id,c.retail_year_week
      HAVING count(DISTINCT s.business_date)=7 AND max(s.business_date)<?
    ), selected_pair AS (
      SELECT e.location_id,e.product_id,e.retail_year_week
      FROM eligible_week e JOIN read_parquet(?) f ON f.location_id=e.location_id AND f.product_id=e.product_id
        AND f.target_retail_year_week=e.retail_year_week
      WHERE f.forecast_created_retail_year_week<f.target_retail_year_week
      QUALIFY row_number() OVER(PARTITION BY e.location_id,e.product_id,e.retail_year_week ORDER BY f.forecast_created_retail_year_week DESC)=1
    )
    SELECT p.location_id,p.product_id,p.retail_year_week,c.calendar_weekday_number,sum(s.units)::DOUBLE units
    FROM selected_pair p JOIN read_parquet(?) c USING(retail_year_week)
    JOIN sales_day s ON s.business_date=c.calendar_date AND s.location_id=p.location_id AND s.product_id=p.product_id
    GROUP BY ALL ORDER BY p.location_id,p.product_id,p.retail_year_week,c.calendar_weekday_number""", [
        _scan(canonical_root, "company_item"), _scan(canonical_root, "product"),
        observation_date, observation_date, observation_date, _scan(canonical_root, "sales_daily"),
        history_start, observation_date, _scan(canonical_root, "inventory_daily"),
        _scan(canonical_root, "calendar_day"), observation_date, _scan(canonical_root, "demand_forecast_weekly"),
        _scan(canonical_root, "calendar_day"),
    ]).fetchall()
    key_weeks: dict[tuple[str, str], set[int]] = defaultdict(set)
    item_pairs: dict[str, set[tuple[str, int]]] = defaultdict(set)
    brand_pairs: set[tuple[str, str, int]] = set()
    key_units: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0] * 7)
    item_units: dict[str, list[float]] = defaultdict(lambda: [0.0] * 7)
    brand_units = [0.0] * 7
    for location, product, week, weekday, units in rows:
        key = (str(location), str(product)); product = str(product); week = int(week); index = int(weekday) - 1
        key_weeks[key].add(week); item_pairs[product].add((str(location), week)); brand_pairs.add((str(location), product, week))
        key_units[key][index] += float(units); item_units[product][index] += float(units); brand_units[index] += float(units)
    keys = {key: (len(key_weeks[key]), units) for key, units in key_units.items()}
    items = {product: (len(item_pairs[product]), units) for product, units in item_units.items()}
    return keys, items, (len(brand_pairs), brand_units)


def _daily_base_forecast(
    connection: duckdb.DuckDBPyConnection,
    canonical_root: Path,
    observation: Observation,
    future: list[ForecastVintage],
    weekday_inputs: tuple[
        dict[tuple[str, str], tuple[int, list[float]]],
        dict[str, tuple[int, list[float]]],
        tuple[int, list[float]],
    ],
) -> list[float]:
    key = (str(observation["store_id"]), str(observation["product_id"]))
    keys, items, brand = weekday_inputs
    key_count, key_units = keys.get(key, (0, [0.0] * 7))
    item_count, item_units = items.get(key[1], (0, [0.0] * 7))
    if key_count >= 4:
        shares = normalize_weekday_shares(key_units)
    elif item_count >= 20:
        shares = normalize_weekday_shares(item_units)
    elif brand[0] >= 20:
        shares = normalize_weekday_shares(brand[1])
    else:
        shares = normalize_weekday_shares([1.0] * 7)
    weekly = {int(row["target_retail_year_week"]): float(row["memento_weekly_demand_base"]) for row in future}
    first_day = observation["observation_date"] + timedelta(days=1)
    last_day = observation["observation_date"] + timedelta(days=28)
    calendar = connection.execute(
        "SELECT calendar_date,retail_year_week,calendar_weekday_number FROM read_parquet(?) "
        "WHERE calendar_date BETWEEN ? AND ? ORDER BY calendar_date",
        [_scan(canonical_root, "calendar_day"), first_day, last_day],
    ).fetchall()
    if len(calendar) != 28 or any(int(week) not in weekly for _, week, _ in calendar):
        return []
    return [weekly[int(week)] * shares[int(weekday) - 1] for _, week, weekday in calendar]


def _load_inbound(connection: duckdb.DuckDBPyConnection, canonical_root: Path, observation: Observation, signal_as_of: datetime) -> dict[date, float]:
    rows = connection.execute("""WITH latest AS (
      SELECT * FROM read_parquet(?) WHERE location_id=? AND product_id=? AND known_at<=?
      QUALIFY row_number() OVER(PARTITION BY retailer_order_id,order_line_number ORDER BY event_version DESC,known_at DESC)=1)
      SELECT expected_store_receipt_date,
        sum(CASE WHEN status_code='cancelled' THEN 0 ELSE greatest(ordered_quantity-received_quantity,0) END)::DOUBLE
      FROM latest WHERE expected_store_receipt_date IS NOT NULL GROUP BY expected_store_receipt_date""", [
        _scan(canonical_root, "replenishment_commitment"), observation["store_id"], observation["product_id"], signal_as_of,
    ]).fetchall()
    return {row[0]: float(row[1]) for row in rows}


def run_signals(
    canonical_root: Path, *, data_root: Path,
    annual_carrying_cost_rate: Decimal,
    carrying_rate_version: str,
) -> Path:
    """Orchestrate independent candidate producers, ranking, and atomic publication."""
    canonical_root = canonical_root.resolve(strict=True)
    if not Decimal("0") <= annual_carrying_cost_rate <= Decimal("1"):
        raise ValueError("annual carrying cost rate must be between zero and one")
    if not carrying_rate_version.strip():
        raise ValueError("carrying rate version is required")
    manifest = json.loads((canonical_root / "manifest.json").read_text())
    tables = {item["path"].split("/", 1)[0] for item in manifest.get("files", [])}
    if "company_item_economics" not in tables:
        raise IngestionFailure("signal_validation", [ValidationResult("SIGNAL_ECONOMICS_REQUIRED", "FAIL", "company_item_economics", 1, "approved unit economics are required")])

    prediction_root = run_predictions(canonical_root, data_root=data_root)
    connection = duckdb.connect()
    observations = _load_observations(connection, canonical_root)
    if not observations:
        raise IngestionFailure("signal_validation", [ValidationResult("SIGNAL_OBSERVATIONS_REQUIRED", "FAIL", count=1, summary="no eligible observations resolved")])
    reactions = _load_reactions(connection, canonical_root, observations[0]["observation_date"])
    weekday_inputs = _load_weekday_inputs(connection, canonical_root, observations[0]["observation_date"])
    signal_as_of = datetime.fromisoformat(str(manifest["as_of"]).replace("Z", "+00:00"))
    batch = build_availability_candidates(connection, prediction_root=prediction_root, observations=observations, canonical_manifest=manifest)

    forecast_rows = connection.execute(
        "SELECT store_id,product_id,target_retail_year_week,memento_weekly_demand_base,forecast_wape FROM read_parquet(?)",
        [str(prediction_root / "demand_forecast_vintage.parquet")],
    ).fetchall()
    forecasts_by_key: dict[tuple[str, str], list[ForecastVintage]] = defaultdict(list)
    for row in forecast_rows:
        forecasts_by_key[(str(row[0]), str(row[1]))].append(ForecastVintage(
            target_retail_year_week=int(row[2]), memento_weekly_demand_base=row[3], forecast_wape=row[4],
        ))

    for observation in observations:
        if (
            float(observation["on_hand"]) < 0
            or observation["price"] is None
            or float(observation["price"]) < 0
            or not observation["assorted"]
            or not observation["replenishment_enabled"]
            or observation["location_status"] not in {"O", "OPEN", "Open"}
        ):
            batch.reason_codes.extend(["demand_momentum_invalid_observation", "inventory_imbalance_invalid_observation"])
            continue
        key = (str(observation["store_id"]), str(observation["product_id"]))
        history = _load_history(connection, canonical_root, observation)
        future = sorted(forecasts_by_key.get(key, []), key=lambda row: row["target_retail_year_week"])
        daily = _daily_base_forecast(connection, canonical_root, observation, future, weekday_inputs)
        if len(daily) != 28:
            batch.reason_codes.extend(["demand_momentum_missing_forward_horizon", "inventory_imbalance_missing_forward_horizon"])
            continue
        minimum_reaction = _minimum_reaction(observation, reactions)
        batch.extend(build_demand_candidate(observation, manifest, weekly_history=history, forward_daily_forecast=daily, minimum_reaction_days=minimum_reaction))
        selected_wape = future[0].get("forecast_wape") if future else None
        forecast_quality = 1 - clamp(float(selected_wape) if selected_wape is not None else 1, 0, 1)
        batch.extend(build_inventory_candidate(
            observation, manifest, forward_daily_forecast=daily, forecast_quality=forecast_quality,
            history_count=len(history), minimum_reaction_days=minimum_reaction,
            inbound_by_date=_load_inbound(connection, canonical_root, observation, signal_as_of),
            annual_carrying_cost_rate=float(annual_carrying_cost_rate),
        ))

    configuration = {
        "annual_carrying_cost_rate": format(annual_carrying_cost_rate, "f"), "carrying_rate_version": carrying_rate_version,
        "momentum_multiplier_range": ["0.50", "1.50"], "weights": {"impact": "0.50", "reaction": "0.30", "confidence": "0.20"},
        "signal_type_order": list(SIGNAL_TYPE_ORDER),
    }
    ranked = rank_signal_candidates(batch.candidates)
    return publish_signal_set(ranked, batch.evidence, canonical_manifest=manifest, data_root=data_root, configuration=configuration, reason_codes=batch.reason_codes)
