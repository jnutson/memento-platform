from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from itertools import groupby
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .manifest import canonical_json, sha256_file
from .metrics import (
    HORIZON_DAYS, bias_factor, confidence_score, data_completeness, demand_paths,
    forecast_wape, impact_scores, normalize_weekday_shares, project_inventory,
    rank_score, reaction_metrics, stable_prediction_id, timing_stability,
)
from .models import IngestionFailure, ValidationResult


METRIC_CONTRACT_VERSION = "miro-oos-metrics-v1.6.0"
DEMAND_FORECAST_VERSION = "miro-interpretable-demand-v1"
INVENTORY_PROJECTION_VERSION = "miro-deterministic-inventory-v1"
RANKER_VERSION = "miro-oos-ranker-v1"
CONFIGURATION = {
    "company_id": "MIRO_TOYS", "brand_id": "MIRO_SPARK", "history_weeks": 8,
    "horizon_days": 28, "display_limit": 10, "minimum_pairs": 6,
    "pooled_minimum_pairs": 20, "minimum_completeness": 0.50,
    "maximum_inbound_reconciliation_rate": 0.10,
    "require_complete_horizon": True,
    "weights": {"impact": 0.50, "reaction": 0.30, "confidence": 0.20},
}
CONFIGURATION_HASH = hashlib.sha256(canonical_json(CONFIGURATION)).hexdigest()


PREDICTION_SCHEMA = pa.schema([
    ("prediction_id", pa.string()), ("prediction_as_of", pa.timestamp("us", tz="UTC")),
    ("prediction_date", pa.date32()), ("company_id", pa.string()), ("brand_id", pa.string()),
    ("store_id", pa.string()), ("product_id", pa.string()), ("predicted_oos_date", pa.date32()),
    ("earliest_oos_date", pa.date32()), ("latest_oos_date", pa.date32()),
    ("estimated_lost_units", pa.decimal128(20, 6)), ("estimated_lost_sales_amount", pa.decimal128(20, 2)),
    ("days_until_predicted_oos", pa.int32()), ("minimum_reaction_days", pa.int32()),
    ("action_slack_days", pa.int32()), ("forecast_wape", pa.decimal128(9, 6)),
    ("forecast_error_band", pa.decimal128(9, 6)), ("forecast_quality", pa.decimal128(9, 6)),
    ("data_completeness", pa.decimal128(9, 6)), ("oos_date_span_days", pa.int32()),
    ("timing_stability_score", pa.decimal128(9, 6)), ("impact_score", pa.decimal128(9, 6)),
    ("reaction_score", pa.decimal128(9, 6)), ("prediction_confidence_score", pa.decimal128(9, 6)),
    ("rank_score", pa.decimal128(9, 6)), ("rank_position", pa.int32()), ("is_top_10", pa.bool_()),
    ("source_release_ids", pa.list_(pa.string())), ("source_release_set_id", pa.string()),
    ("metric_contract_version", pa.string()), ("demand_forecast_version", pa.string()),
    ("inventory_projection_version", pa.string()), ("ranker_version", pa.string()),
    ("configuration_hash", pa.string()),
])

EVIDENCE_SCHEMA = pa.schema([
    ("prediction_id", pa.string()), ("projection_date", pa.date32()), ("path", pa.string()),
    ("demand_units", pa.decimal128(20, 6)), ("scheduled_inbound_units", pa.decimal128(20, 6)),
    ("opening_units", pa.decimal128(20, 6)), ("available_units", pa.decimal128(20, 6)),
    ("fulfilled_units", pa.decimal128(20, 6)), ("lost_units", pa.decimal128(20, 6)),
    ("projected_ending_on_hand_units", pa.decimal128(20, 6)),
])

FORECAST_SCHEMA = pa.schema([
    ("prediction_as_of", pa.timestamp("us", tz="UTC")), ("store_id", pa.string()),
    ("product_id", pa.string()), ("target_retail_year_week", pa.int32()),
    ("retailer_forecast_units", pa.decimal128(20, 6)), ("forecast_bias_factor", pa.decimal128(9, 6)),
    ("memento_weekly_demand_base", pa.decimal128(20, 6)), ("forecast_wape", pa.decimal128(9, 6)),
    ("fallback_level", pa.string()),
])


def _scan(root: Path, table: str) -> str:
    pattern = str(root / table / "*.parquet").replace("'", "''")
    return f"read_parquet('{pattern}')"


def _decimal(value: float, scale: int) -> Decimal:
    quantum = Decimal(1).scaleb(-scale)
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_EVEN)


def _require_canonical(root: Path) -> dict[str, object]:
    path = root / "manifest.json"
    if not path.is_file() or path.is_symlink():
        raise IngestionFailure("prediction_validation", [ValidationResult("PRED_CANONICAL_MANIFEST", "FAIL", count=1, summary="canonical manifest missing or unsafe")])
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {"calendar_day", "location", "product", "sales_daily", "inventory_daily", "demand_forecast_weekly", "company_item", "replenishment_commitment", "reaction_constraint"}
    present = {entry["path"].split("/", 1)[0] for entry in manifest.get("files", [])}
    if present not in (required, required | {"company_item_economics"}):
        raise IngestionFailure("prediction_validation", [ValidationResult("PRED_CANONICAL_DATASETS", "FAIL", count=1, summary="exact legacy nine or signal ten canonical datasets required")])
    for entry in manifest["files"]:
        file = root / entry["path"]
        if not file.is_file() or file.is_symlink() or file.stat().st_size != entry["bytes"] or sha256_file(file) != entry["sha256"]:
            raise IngestionFailure("prediction_validation", [ValidationResult("PRED_CANONICAL_HASH", "FAIL", count=1, summary="canonical file does not match manifest")])
    return manifest


def _publish_current(predictions_root: Path, prediction_set_id: str) -> None:
    pointer = canonical_json({"prediction_set_id": prediction_set_id, "manifest": f"{prediction_set_id}/manifest.json"})
    temporary = predictions_root / f".current-{uuid.uuid4().hex}.tmp"
    temporary.write_bytes(pointer)
    os.replace(temporary, predictions_root / "current.json")


def _stats_bias(stats: list[float], minimum_count: int) -> float | None:
    count, actual, forecast = stats
    if count < minimum_count or forecast <= 0:
        return None
    return min(max(actual / forecast, 0.5), 1.5)


def _choose_bias(key, product_id, pairs_by_key, item_stats, brand_stats):
    own = pairs_by_key.get(key, [])[-8:]
    if len(own) >= 6 and bias_factor(own) is not None:
        return bias_factor(own), "store_item"
    item_bias = _stats_bias(item_stats[product_id], 20)
    if item_bias is not None:
        return item_bias, "item"
    brand_bias = _stats_bias(brand_stats, 20)
    if brand_bias is not None:
        return brand_bias, "brand"
    return 1.0, "default"


def _stats_wape(stats: list[float], minimum_count: int) -> float | None:
    count, actual, absolute_error = stats
    if count < minimum_count or actual <= 0:
        return None
    return absolute_error / actual


def _choose_wape(key, product_id, pairs_by_key, item_stats, brand_stats):
    own = pairs_by_key.get(key, [])[-8:]
    if len(own) >= 6:
        return forecast_wape(own)
    item_wape = _stats_wape(item_stats[product_id], 20)
    if item_wape is not None:
        return item_wape
    return _stats_wape(brand_stats, 20)


def run_predictions(canonical_root: Path, *, data_root: Path) -> Path:
    canonical_root = canonical_root.resolve(strict=True)
    source_manifest = _require_canonical(canonical_root)
    identity = {
        "canonical_dataset_id": source_manifest["dataset_id"], "metric_contract_version": METRIC_CONTRACT_VERSION,
        "demand_forecast_version": DEMAND_FORECAST_VERSION, "inventory_projection_version": INVENTORY_PROJECTION_VERSION,
        "ranker_version": RANKER_VERSION, "configuration_hash": CONFIGURATION_HASH,
    }
    prediction_set_id = "mps_" + hashlib.sha256(canonical_json(identity)).hexdigest()
    published = data_root.resolve() / "predictions" / prediction_set_id
    if (published / "manifest.json").is_file():
        manifest = json.loads((published / "manifest.json").read_text())
        if manifest.get("prediction_set_id") == prediction_set_id and manifest.get("canonical_dataset_id") == source_manifest["dataset_id"] and len(manifest.get("files", [])) == 3 and all((published / f["path"]).is_file() and sha256_file(published / f["path"]) == f["sha256"] for f in manifest.get("files", [])):
            return published
        raise IngestionFailure("published_validation", [ValidationResult("PRED_IMMUTABLE_INTACT", "FAIL", count=1, summary="published prediction set differs from manifest")])

    run_id = "run_" + uuid.uuid4().hex
    stage = data_root.resolve() / "staging" / run_id / "predictions"
    try:
        stage.mkdir(parents=True, exist_ok=False)
        con = duckdb.connect()
        for table in ("calendar_day", "location", "product", "sales_daily", "inventory_daily", "demand_forecast_weekly", "company_item", "replenishment_commitment", "reaction_constraint"):
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM {_scan(canonical_root, table)}")
        as_of = datetime.fromisoformat(str(source_manifest["as_of"]).replace("Z", "+00:00"))
        observation_date = con.execute("SELECT max(business_date) FROM inventory_daily WHERE business_date < ?", [as_of.date()]).fetchone()[0]
        if observation_date is None:
            raise ValueError("no closed inventory observation exists")
        horizon = [observation_date + timedelta(days=offset) for offset in range(1, HORIZON_DAYS + 1)]
        history_start = observation_date - timedelta(days=55)
        horizon_calendar_count = con.execute(
            "SELECT count(DISTINCT calendar_date) FROM calendar_day WHERE calendar_date BETWEEN ? AND ?",
            [horizon[0], horizon[-1]],
        ).fetchone()[0]
        if horizon_calendar_count != HORIZON_DAYS:
            raise IngestionFailure("prediction_validation", [ValidationResult("PRED_HORIZON_CALENDAR", "FAIL", "calendar_day", HORIZON_DAYS - int(horizon_calendar_count), "complete 28-day forward calendar required")])
        target_week_count = con.execute(
            "SELECT count(DISTINCT retail_year_week) FROM calendar_day WHERE calendar_date BETWEEN ? AND ?",
            [horizon[0], horizon[-1]],
        ).fetchone()[0]

        con.execute("""CREATE TEMP TABLE scoped AS
            SELECT c.product_id,c.company_item_id FROM company_item c JOIN product p USING(product_id)
            WHERE c.company_id='MIRO_TOYS' AND c.display_brand_id='MIRO_SPARK' AND p.brand_name='BRAND_A'
              AND upper(p.source_status_code) IN ('A','ACTIVE') AND p.effective_date<=? AND p.replenishment_enabled
              AND c.effective_from<=? AND (c.effective_to IS NULL OR c.effective_to>=?)""", [observation_date, observation_date, observation_date])
        con.execute("""CREATE TEMP TABLE sales_day AS
            SELECT business_date,location_id,product_id,sum(sales_quantity)::DOUBLE units,sum(sales_amount)::DOUBLE amount
            FROM sales_daily WHERE business_date BETWEEN ? AND ? GROUP BY ALL""", [history_start, observation_date])
        con.execute("""CREATE TEMP TABLE eligible_week AS
            SELECT s.location_id,s.product_id,c.retail_year_week,sum(s.units)::DOUBLE actual_units
            FROM sales_day s JOIN scoped q USING(product_id) JOIN inventory_daily i USING(business_date,location_id,product_id)
            JOIN calendar_day c ON c.calendar_date=s.business_date
            WHERE s.units>=0 AND i.on_hand_quantity>=0 AND i.assorted AND i.replenishment_enabled
              AND NOT (i.on_hand_quantity=0 AND i.assorted AND i.replenishment_enabled)
            GROUP BY s.location_id,s.product_id,c.retail_year_week
            HAVING count(DISTINCT s.business_date)=7 AND max(s.business_date)<?""", [observation_date])
        con.execute("""CREATE TEMP TABLE selected_pair AS
            SELECT e.location_id,e.product_id,e.retail_year_week,e.actual_units,f.forecast_quantity::DOUBLE retailer_forecast
            FROM eligible_week e JOIN demand_forecast_weekly f ON f.location_id=e.location_id AND f.product_id=e.product_id AND f.target_retail_year_week=e.retail_year_week
            WHERE f.forecast_created_retail_year_week<f.target_retail_year_week
            QUALIFY row_number() OVER(PARTITION BY e.location_id,e.product_id,e.retail_year_week ORDER BY f.forecast_created_retail_year_week DESC)=1""")
        pair_rows = con.execute("SELECT location_id,product_id,retail_year_week,actual_units,retailer_forecast FROM selected_pair ORDER BY retail_year_week,location_id,product_id").fetchall()
        pairs_by_key = defaultdict(list)
        raw_item_stats = defaultdict(lambda: [0.0, 0.0, 0.0]); raw_brand_stats = [0.0, 0.0, 0.0]
        frozen_by_key = defaultdict(list)
        frozen_item_stats = defaultdict(lambda: [0.0, 0.0, 0.0]); frozen_brand_stats = [0.0, 0.0, 0.0]
        # Reconstruct historical Memento vintages chronologically. All forecasts for a
        # target week are calculated before that week's actuals enter any history pool.
        for _, week_group in groupby(pair_rows, key=lambda row: row[2]):
            group = list(week_group)
            frozen_group = []
            for location, product, _, actual, retailer in group:
                historical_bias, _ = _choose_bias((location, product), product, pairs_by_key, raw_item_stats, raw_brand_stats)
                frozen_group.append((location, product, (float(actual), float(retailer) * historical_bias), (float(actual), float(retailer))))
            for location, product, frozen, raw in frozen_group:
                frozen_by_key[(location, product)].append(frozen)
                frozen_error = abs(frozen[0] - frozen[1])
                for stats in (frozen_item_stats[product], frozen_brand_stats):
                    stats[0] += 1; stats[1] += frozen[0]; stats[2] += frozen_error
                pairs_by_key[(location, product)].append(raw)
                for stats in (raw_item_stats[product], raw_brand_stats):
                    stats[0] += 1; stats[1] += raw[0]; stats[2] += raw[1]

        weekday_rows = con.execute("""SELECT e.location_id,e.product_id,c.calendar_weekday_number,sum(s.units)::DOUBLE units
            FROM eligible_week e JOIN calendar_day c USING(retail_year_week)
            JOIN sales_day s ON s.business_date=c.calendar_date AND s.location_id=e.location_id AND s.product_id=e.product_id
            GROUP BY ALL ORDER BY e.location_id,e.product_id,c.calendar_weekday_number""").fetchall()
        weekday_key = defaultdict(lambda: [0.0] * 7); weekday_item = defaultdict(lambda: [0.0] * 7); weekday_brand = [0.0] * 7
        for location, product, weekday, units in weekday_rows:
            index = int(weekday) - 1; value = float(units)
            weekday_key[(location, product)][index] += value; weekday_item[product][index] += value; weekday_brand[index] += value

        future_forecasts = con.execute("""SELECT f.location_id,f.product_id,f.target_retail_year_week,f.forecast_quantity::DOUBLE
            FROM demand_forecast_weekly f JOIN scoped s USING(product_id)
            JOIN (SELECT DISTINCT retail_year_week FROM calendar_day WHERE calendar_date BETWEEN ? AND ?) w ON w.retail_year_week=f.target_retail_year_week
            WHERE f.forecast_created_retail_year_week<f.target_retail_year_week
            QUALIFY row_number() OVER(PARTITION BY f.location_id,f.product_id,f.target_retail_year_week ORDER BY f.forecast_created_retail_year_week DESC)=1
            ORDER BY f.location_id,f.product_id,f.target_retail_year_week""", [horizon[0], horizon[-1]]).fetchall()
        future_by_key = defaultdict(dict)
        for location, product, week, value in future_forecasts:
            future_by_key[(location, product)][int(week)] = float(value)

        inbound_rows = con.execute("""WITH latest AS (
              SELECT * FROM replenishment_commitment WHERE known_at<=?
              QUALIFY row_number() OVER(PARTITION BY retailer_order_id,order_line_number ORDER BY event_version DESC)=1)
            SELECT location_id,product_id,expected_store_receipt_date,sum(greatest(ordered_quantity-received_quantity,0))::DOUBLE
            FROM latest WHERE status_code<>'cancelled' AND expected_store_receipt_date>? AND expected_store_receipt_date<=?
            GROUP BY ALL""", [as_of, observation_date, horizon[-1]]).fetchall()
        inbound_by_key = defaultdict(dict)
        for location, product, day, units in inbound_rows:
            inbound_by_key[(location, product)][day] = float(units)

        observation_rows = con.execute("""SELECT i.location_id,i.product_id,i.on_hand_quantity::DOUBLE,
              CASE WHEN s.units>0 THEN s.amount/s.units ELSE i.current_unit_retail_amount END::DOUBLE applicable_unit_price,
              i.assorted,i.replenishment_enabled,l.source_status_code
            FROM inventory_daily i JOIN scoped q USING(product_id) JOIN location l USING(location_id)
            LEFT JOIN sales_day s USING(business_date,location_id,product_id)
            WHERE i.business_date=? ORDER BY i.location_id,i.product_id""", [observation_date]).fetchall()
        expected_forecast_rows = len(observation_rows) * int(target_week_count)
        if not observation_rows or len(future_forecasts) != expected_forecast_rows:
            raise IngestionFailure("prediction_validation", [ValidationResult("PRED_FORWARD_FORECAST_COVERAGE", "FAIL", "demand_forecast_weekly", abs(expected_forecast_rows - len(future_forecasts)), "one eligible forecast per scoped store-item target week required")])
        coverage_rows = con.execute("""SELECT i.location_id,i.product_id,count(DISTINCT s.business_date) FILTER(WHERE s.units>=0) valid_sales_days,count(DISTINCT i.business_date) valid_inventory_days
            FROM inventory_daily i JOIN scoped q USING(product_id) LEFT JOIN sales_day s USING(business_date,location_id,product_id)
            WHERE i.business_date BETWEEN ? AND ? AND i.on_hand_quantity>=0 GROUP BY i.location_id,i.product_id""", [history_start, observation_date]).fetchall()
        coverage = {(row[0], row[1]): (int(row[2]), int(row[3])) for row in coverage_rows}
        reconciliation_rows = con.execute("""WITH versions AS (
              SELECT *,lag(received_quantity,1,0) OVER(PARTITION BY retailer_order_id,order_line_number ORDER BY event_version) prior_received
              FROM replenishment_commitment WHERE known_at<=?
            ), latest AS (
              SELECT * FROM versions QUALIFY row_number() OVER(PARTITION BY retailer_order_id,order_line_number ORDER BY event_version DESC)=1
            ), derived AS (
              SELECT location_id,product_id,
                sum(CASE WHEN status_code='cancelled' THEN 0 ELSE greatest(ordered_quantity-invoiced_quantity,0) END)::DOUBLE open_units,
                sum(CASE WHEN status_code='cancelled' THEN 0 ELSE greatest(invoiced_quantity-received_quantity,0) END)::DOUBLE transit_units
              FROM latest GROUP BY ALL
            ), receipts AS (
              SELECT location_id,product_id,sum(greatest(received_quantity-prior_received,0))::DOUBLE receipt_units
              FROM versions WHERE cast(known_at AS DATE)=? GROUP BY ALL
            )
            SELECT i.location_id,i.product_id,greatest(
              abs(coalesce(d.open_units,0)-i.on_order_quantity)/greatest(coalesce(d.open_units,0),i.on_order_quantity,1),
              abs(coalesce(d.transit_units,0)-i.in_transit_quantity)/greatest(coalesce(d.transit_units,0),i.in_transit_quantity,1),
              abs(coalesce(r.receipt_units,0)-i.receipt_quantity)/greatest(coalesce(r.receipt_units,0),i.receipt_quantity,1)
            )::DOUBLE rate
            FROM inventory_daily i JOIN scoped s USING(product_id)
            LEFT JOIN derived d USING(location_id,product_id) LEFT JOIN receipts r USING(location_id,product_id)
            WHERE i.business_date=?""", [as_of, observation_date, observation_date]).fetchall()
        reconciliation = {(row[0], row[1]): float(row[2]) for row in reconciliation_rows}

        reaction_rows = con.execute("SELECT item_scope_type_code,item_scope_id,minimum_reaction_days FROM reaction_constraint WHERE company_id='MIRO_TOYS' AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)", [observation_date, observation_date]).fetchall()
        reaction = {(scope, value): int(days) for scope, value, days in reaction_rows}
        all_reaction = next((int(days) for scope, _, days in reaction_rows if scope == "all"), None)
        item_ids = dict(con.execute("SELECT product_id,company_item_id FROM scoped").fetchall())
        calendar_values = {row[0]: (int(row[1]), int(row[2])) for row in con.execute("SELECT calendar_date,retail_year_week,calendar_weekday_number FROM calendar_day WHERE calendar_date BETWEEN ? AND ?", [horizon[0], horizon[-1]]).fetchall()}

        candidates = []; evidence_by_id = {}; forecasts = []; reason_codes = []
        for location, product, on_hand, price, assorted, replenishable, location_status in observation_rows:
            key = (location, product)
            if on_hand < 0 or price is None or price < 0 or not assorted or not replenishable or location_status not in {"O", "OPEN", "Open"}:
                reason_codes.append("availability_invalid_observation")
                continue
            bias, fallback = _choose_bias(key, product, pairs_by_key, raw_item_stats, raw_brand_stats)
            wape = _choose_wape(key, product, frozen_by_key, frozen_item_stats, frozen_brand_stats)
            band = min(max(wape if wape is not None else 1.0, 0), 1)
            if len(pairs_by_key.get(key, [])) >= 4:
                shares = normalize_weekday_shares(weekday_key[key])
            elif raw_item_stats[product][0] >= 20:
                shares = normalize_weekday_shares(weekday_item[product])
            elif raw_brand_stats[0] >= 20:
                shares = normalize_weekday_shares(weekday_brand)
            else:
                shares = normalize_weekday_shares([1] * 7)
            daily_base = []
            missing = False
            for day in horizon:
                calendar_value = calendar_values.get(day)
                week = calendar_value[0] if calendar_value is not None else None
                retailer = future_by_key[key].get(week) if week is not None else None
                if retailer is None:
                    missing = True; break
                daily_base.append(retailer * bias * shares[calendar_value[1] - 1])
            if missing:
                reason_codes.append("availability_missing_forward_horizon")
                continue
            for week, retailer in sorted(future_by_key[key].items()):
                forecasts.append({"prediction_as_of": as_of, "store_id": location, "product_id": product, "target_retail_year_week": week, "retailer_forecast_units": _decimal(retailer, 6), "forecast_bias_factor": _decimal(bias, 6), "memento_weekly_demand_base": _decimal(retailer * bias, 6), "forecast_wape": _decimal(wape, 6) if wape is not None else None, "fallback_level": fallback})
            paths = {name: [] for name in ("low", "base", "high")}
            for value in daily_base:
                values = demand_paths(value, band)
                for name in paths: paths[name].append(values[name])
            trace, oos = project_inventory(float(on_hand), horizon, paths, inbound_by_key[key])
            predicted = oos["base"]
            if predicted is None:
                reason_codes.append("availability_no_base_oos")
                continue
            base_lost = sum(row.lost_units for row in trace if row.path == "base")
            lost_sales = base_lost * float(price)
            if lost_sales <= 0:
                reason_codes.append("availability_no_lost_sales")
                continue
            sales_days, inventory_days = coverage.get(key, (0, 0))
            completeness = data_completeness(sales_days, 56, inventory_days, 56, len(pairs_by_key.get(key, [])), reconciliation.get(key, 1.0))
            if completeness < 0.50:
                reason_codes.append("availability_insufficient_completeness")
                continue
            minimum_reaction = reaction.get(("item", item_ids[product]), reaction.get(("brand", "MIRO_SPARK"), all_reaction))
            if minimum_reaction is None:
                raise ValueError(f"no reaction constraint for product {product}")
            days_until = (predicted - observation_date).days
            slack, reaction_value = reaction_metrics(days_until, minimum_reaction)
            span, stability = timing_stability(oos["high"], predicted, oos["low"])
            quality, confidence = confidence_score(wape, completeness, stability or 0.0)
            prediction_id = stable_prediction_id(source_manifest["source_release_set_id"], str(source_manifest["as_of"]), location, product, predicted)
            candidates.append({"prediction_id": prediction_id, "prediction_as_of": as_of, "prediction_date": observation_date, "company_id": "MIRO_TOYS", "brand_id": "MIRO_SPARK", "store_id": location, "product_id": product, "predicted_oos_date": predicted, "earliest_oos_date": oos["high"], "latest_oos_date": oos["low"], "estimated_lost_units": _decimal(base_lost, 6), "estimated_lost_sales_amount": _decimal(lost_sales, 2), "days_until_predicted_oos": days_until, "minimum_reaction_days": minimum_reaction, "action_slack_days": slack, "forecast_wape": _decimal(wape, 6) if wape is not None else None, "forecast_error_band": _decimal(band, 6), "forecast_quality": _decimal(quality, 6), "data_completeness": _decimal(completeness, 6), "oos_date_span_days": span, "timing_stability_score": _decimal(stability or 0, 6), "reaction_score": _decimal(reaction_value, 6), "prediction_confidence_score": _decimal(confidence, 6), "source_release_ids": source_manifest["source_release_ids"], "source_release_set_id": source_manifest["source_release_set_id"], "metric_contract_version": METRIC_CONTRACT_VERSION, "demand_forecast_version": DEMAND_FORECAST_VERSION, "inventory_projection_version": INVENTORY_PROJECTION_VERSION, "ranker_version": RANKER_VERSION, "configuration_hash": CONFIGURATION_HASH})
            evidence_by_id[prediction_id] = trace

        impacts = impact_scores([float(row["estimated_lost_sales_amount"]) for row in candidates])
        for row, impact in zip(candidates, impacts, strict=True):
            row["impact_score"] = _decimal(impact, 6)
            row["rank_score"] = _decimal(rank_score(impact, float(row["reaction_score"]), float(row["prediction_confidence_score"])), 6)
        candidates.sort(key=lambda row: (-float(row["rank_score"]), -float(row["estimated_lost_sales_amount"]), row["predicted_oos_date"], row["store_id"], row["product_id"]))
        evidence = []
        for position, row in enumerate(candidates, 1):
            row["rank_position"] = position; row["is_top_10"] = position <= 10
            for trace in evidence_by_id[row["prediction_id"]]:
                evidence.append({"prediction_id": row["prediction_id"], "projection_date": trace.date, "path": trace.path, "demand_units": _decimal(trace.demand_units, 6), "scheduled_inbound_units": _decimal(trace.inbound_units, 6), "opening_units": _decimal(trace.opening_units, 6), "available_units": _decimal(trace.available_units, 6), "fulfilled_units": _decimal(trace.fulfilled_units, 6), "lost_units": _decimal(trace.lost_units, 6), "projected_ending_on_hand_units": _decimal(trace.ending_units, 6)})

        outputs = (("oos_prediction.parquet", candidates, PREDICTION_SCHEMA), ("oos_prediction_evidence.parquet", evidence, EVIDENCE_SCHEMA), ("demand_forecast_vintage.parquet", forecasts, FORECAST_SCHEMA))
        files = []
        for name, rows, schema in outputs:
            path = stage / name
            table = pa.Table.from_pylist(rows, schema=schema)
            pq.write_table(table, path, compression="zstd", row_group_size=122_880)
            files.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256_file(path), "rows": table.num_rows})
        manifest = {"prediction_set_id": prediction_set_id, **identity, "prediction_as_of": source_manifest["as_of"], "prediction_date": observation_date.isoformat(), "source_release_set_id": source_manifest["source_release_set_id"], "source_release_set_manifest_sha256": source_manifest.get("source_release_set_manifest_sha256"), "source_release_ids": source_manifest["source_release_ids"], "source_manifests": source_manifest["source_manifests"], "candidate_count": len(candidates), "display_count": min(len(candidates), 10), "reason_code_counts": dict(sorted(Counter(reason_codes).items())), "files": files}
        (stage / "manifest.json").write_bytes(canonical_json(manifest))
        published.parent.mkdir(parents=True, exist_ok=True)
        os.rename(stage, published)
        _publish_current(published.parent, prediction_set_id)
        return published
    except Exception:
        raise
    finally:
        run_root = data_root.resolve() / "staging" / run_id
        if run_root.exists(): shutil.rmtree(run_root)
