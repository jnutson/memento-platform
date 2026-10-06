import hashlib
import json
import shutil
from pathlib import Path

import duckdb

from memento.prediction import run_predictions
from memento.evaluation import evaluate_predictions
from memento.serving import PredictionStore


def _canonical_fixture(root: Path) -> Path:
    canonical = root / "canonical"
    canonical.mkdir()
    con = duckdb.connect()
    start = "2026-12-05"
    end = "2027-02-26"
    history_end = "2027-01-29"
    queries = {
        "calendar_day": f"""SELECT d::DATE calendar_date,(202649+floor(date_diff('day',DATE '{start}',d)/7))::INTEGER retail_year_week,isodow(d)::INTEGER calendar_weekday_number FROM range(DATE '{start}',DATE '{end}'+1,INTERVAL 1 DAY) t(d)""",
        "location": """SELECT 'loc_test'::VARCHAR location_id,'10'::VARCHAR source_location_id,'Synthetic Store 10'::VARCHAR location_name,'O'::VARCHAR source_status_code""",
        "product": """SELECT 'prd_test'::VARCHAR product_id,'BRAND_A'::VARCHAR brand_name,'ACTIVE'::VARCHAR source_status_code,DATE '2026-01-01' effective_date,true::BOOLEAN replenishment_enabled""",
        "sales_daily": f"""SELECT d::DATE business_date,'loc_test'::VARCHAR location_id,'prd_test'::VARCHAR product_id,1::BIGINT sales_quantity,10.00::DECIMAL(20,2) sales_amount FROM range(DATE '{start}',DATE '{history_end}'+1,INTERVAL 1 DAY) t(d)""",
        "inventory_daily": f"""SELECT d::DATE business_date,'loc_test'::VARCHAR location_id,'prd_test'::VARCHAR product_id,CASE WHEN d=DATE '{history_end}' THEN 2 ELSE 100 END::BIGINT on_hand_quantity,0::BIGINT on_order_quantity,0::BIGINT in_transit_quantity,0::BIGINT receipt_quantity,true::BOOLEAN assorted,true::BOOLEAN replenishment_enabled,10.00::DECIMAL(20,2) current_unit_retail_amount FROM range(DATE '{start}',DATE '{history_end}'+1,INTERVAL 1 DAY) t(d)""",
        "demand_forecast_weekly": f"""SELECT DISTINCT (202648+floor(date_diff('day',DATE '{start}',d)/7))::INTEGER forecast_created_retail_year_week,(202649+floor(date_diff('day',DATE '{start}',d)/7))::INTEGER target_retail_year_week,'loc_test'::VARCHAR location_id,'prd_test'::VARCHAR product_id,7.0::DECIMAL(20,6) forecast_quantity FROM range(DATE '{start}',DATE '{end}'+1,INTERVAL 7 DAY) t(d)""",
        "company_item": """SELECT 'MIRO_TOYS'::VARCHAR company_id,'MIRO-SPARK-001'::VARCHAR company_item_id,'Miro Spark One'::VARCHAR company_item_name,'MIRO_SPARK'::VARCHAR display_brand_id,'prd_test'::VARCHAR product_id,'0'::VARCHAR source_company_id,'100'::VARCHAR source_product_id,DATE '2026-01-01' effective_from,NULL::DATE effective_to""",
        "replenishment_commitment": """SELECT * FROM (SELECT NULL::VARCHAR retailer_order_id,NULL::INTEGER order_line_number,NULL::INTEGER event_version,NULL::VARCHAR location_id,NULL::VARCHAR product_id,NULL::BIGINT ordered_quantity,NULL::BIGINT invoiced_quantity,NULL::BIGINT received_quantity,NULL::TIMESTAMPTZ order_created_at,NULL::TIMESTAMPTZ approved_to_ship_at,NULL::TIMESTAMPTZ dc_invoiced_at,NULL::DATE expected_store_receipt_date,NULL::TIMESTAMPTZ actual_store_receipt_at,NULL::VARCHAR status_code,NULL::TIMESTAMPTZ known_at) WHERE false""",
        "reaction_constraint": """SELECT 'MIRO_TOYS'::VARCHAR company_id,'brand'::VARCHAR item_scope_type_code,'MIRO_SPARK'::VARCHAR item_scope_id,10::INTEGER minimum_reaction_days,DATE '2026-01-01' effective_from,NULL::DATE effective_to""",
        "company_item_economics": """SELECT 'MIRO_TOYS'::VARCHAR company_id,'MIRO-SPARK-001'::VARCHAR company_item_id,'USD'::VARCHAR currency_code,4.00::DECIMAL(20,2) unit_cost_amount,DATE '2026-01-01' effective_from,NULL::DATE effective_to""",
    }
    files = []
    for table, query in queries.items():
        folder = canonical / table
        folder.mkdir()
        path = folder / "part-00000.parquet"
        con.execute(f"COPY ({query}) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        files.append({"path": str(path.relative_to(canonical)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": con.execute(f"SELECT count(*) FROM ({query})").fetchone()[0]})
    manifest = {"dataset_id": "mds_fixture", "as_of": "2027-01-30T12:00:00Z", "source_release_set_id": "fixture-release-set", "source_release_set_manifest_sha256": "c" * 64, "source_release_ids": ["fixture-walmart", "fixture-extension"], "source_manifests": {"walmart_sha256": "a" * 64, "extension_sha256": "b" * 64}, "files": files}
    (canonical / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    return canonical


def test_prediction_pipeline_publishes_ranked_evidence_and_replays(tmp_path: Path):
    canonical = _canonical_fixture(tmp_path)
    output = run_predictions(canonical, data_root=tmp_path / "data")
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["candidate_count"] == 1
    assert manifest["display_count"] == 1
    assert manifest["reason_code_counts"] == {}
    con = duckdb.connect()
    prediction = con.execute("SELECT predicted_oos_date,rank_position,is_top_10,impact_score FROM read_parquet(?)", [str(output / "oos_prediction.parquet")]).fetchone()
    assert str(prediction[0]) == "2027-01-31"
    assert prediction[1:] == (1, True, 1)
    assert con.execute("SELECT count(*) FROM read_parquet(?)", [str(output / "oos_prediction_evidence.parquet")]).fetchone()[0] == 84
    store = PredictionStore(tmp_path / "data" / "predictions")
    top = store.top_predictions()
    assert len(top) == 1 and top[0]["rank_position"] == 1
    assert len(store.evidence(top[0]["prediction_id"])) == 84
    before = (output / "manifest.json").read_bytes()
    assert run_predictions(canonical, data_root=tmp_path / "data") == output
    assert (output / "manifest.json").read_bytes() == before


def test_prediction_pipeline_reports_suppressed_availability_candidate(tmp_path: Path):
    canonical = _canonical_fixture(tmp_path)
    inventory = canonical / "inventory_daily" / "part-00000.parquet"
    replacement = canonical / "inventory_daily" / "replacement.parquet"
    con = duckdb.connect()
    con.execute("CREATE TEMP TABLE rewritten_inventory AS SELECT * REPLACE (100::BIGINT AS on_hand_quantity) FROM read_parquet(?)", [str(inventory)])
    con.execute("COPY rewritten_inventory TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(replacement)])
    replacement.replace(inventory)
    manifest = json.loads((canonical / "manifest.json").read_text())
    for entry in manifest["files"]:
        if entry["path"] == "inventory_daily/part-00000.parquet":
            entry.update(bytes=inventory.stat().st_size, sha256=hashlib.sha256(inventory.read_bytes()).hexdigest())
    (canonical / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))

    output = run_predictions(canonical, data_root=tmp_path / "data")
    result = json.loads((output / "manifest.json").read_text())
    assert result["candidate_count"] == 0
    assert result["reason_code_counts"] == {"availability_no_base_oos": 1}


def test_matured_prediction_evaluation_uses_only_later_observations(tmp_path: Path):
    canonical = _canonical_fixture(tmp_path)
    prediction = run_predictions(canonical, data_root=tmp_path / "data")
    later = tmp_path / "later-canonical"
    shutil.copytree(canonical, later)
    inventory = later / "inventory_daily" / "part-00000.parquet"
    con = duckdb.connect()
    replacement = later / "inventory_daily" / "replacement.parquet"
    con.execute(f"""COPY (SELECT d::DATE business_date,'loc_test'::VARCHAR location_id,'prd_test'::VARCHAR product_id,
      CASE WHEN d>=DATE '2027-01-31' THEN 0 ELSE 100 END::BIGINT on_hand_quantity,0::BIGINT on_order_quantity,
      0::BIGINT in_transit_quantity,0::BIGINT receipt_quantity,true::BOOLEAN assorted,true::BOOLEAN replenishment_enabled,
      10.00::DECIMAL(20,2) current_unit_retail_amount
      FROM range(DATE '2026-12-05',DATE '2027-02-26'+1,INTERVAL 1 DAY) t(d))
      TO '{replacement}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    replacement.replace(inventory)
    manifest = json.loads((later / "manifest.json").read_text())
    manifest["dataset_id"] = "mds_later_fixture"
    manifest["source_release_set_id"] = "later-release-set"
    for entry in manifest["files"]:
        if entry["path"] == "inventory_daily/part-00000.parquet":
            entry.update(bytes=inventory.stat().st_size, sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(), rows=84)
    (later / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    evaluation = evaluate_predictions(prediction, later, data_root=tmp_path / "data")
    result = duckdb.connect().execute("SELECT oos_outcome,actual_first_oos_date,lead_time_error_days,evaluable FROM read_parquet(?)", [str(evaluation / "oos_evaluation.parquet")]).fetchone()
    assert result == (True, __import__("datetime").date(2027, 1, 31), 0, True)
    evaluation_manifest = json.loads((evaluation / "manifest.json").read_text())
    assert evaluation_manifest["precision_at_10"] == 1.0
