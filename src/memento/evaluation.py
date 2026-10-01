from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .manifest import canonical_json, sha256_file


EVALUATION_VERSION = "miro-oos-evaluation-v1"
SCHEMA = pa.schema([
    ("prediction_id", pa.string()), ("prediction_set_id", pa.string()),
    ("predicted_oos_date", pa.date32()), ("actual_first_oos_date", pa.date32()),
    ("oos_outcome", pa.bool_()), ("lead_time_error_days", pa.int32()),
    ("absolute_lead_time_error_days", pa.int32()), ("was_displayed", pa.bool_()),
    ("evaluable", pa.bool_()), ("reason_code", pa.string()),
])


def evaluate_predictions(prediction_root: Path, later_canonical_root: Path, *, data_root: Path) -> Path:
    prediction_root = prediction_root.resolve(strict=True)
    later_canonical_root = later_canonical_root.resolve(strict=True)
    prediction_manifest = json.loads((prediction_root / "manifest.json").read_text())
    canonical_manifest = json.loads((later_canonical_root / "manifest.json").read_text())
    for item in prediction_manifest.get("files", []):
        file = prediction_root / item["path"]
        if not file.is_file() or file.is_symlink() or file.stat().st_size != item["bytes"] or sha256_file(file) != item["sha256"]:
            raise ValueError("prediction release integrity failure")
    for item in canonical_manifest.get("files", []):
        file = later_canonical_root / item["path"]
        if not file.is_file() or file.is_symlink() or file.stat().st_size != item["bytes"] or sha256_file(file) != item["sha256"]:
            raise ValueError("evaluation source integrity failure")
    identity = {
        "prediction_set_id": prediction_manifest["prediction_set_id"],
        "evaluation_source_dataset_id": canonical_manifest["dataset_id"],
        "evaluation_version": EVALUATION_VERSION,
    }
    evaluation_id = "mev_" + hashlib.sha256(canonical_json(identity)).hexdigest()
    published = data_root.resolve() / "evaluations" / evaluation_id
    if (published / "manifest.json").is_file():
        existing = json.loads((published / "manifest.json").read_text())
        if existing.get("evaluation_id") == evaluation_id and all((published / item["path"]).is_file() and sha256_file(published / item["path"]) == item["sha256"] for item in existing.get("files", [])):
            return published
        raise ValueError("published evaluation integrity failure")
    run_id = "run_" + uuid.uuid4().hex
    stage = data_root.resolve() / "staging" / run_id / "evaluation"
    try:
        stage.mkdir(parents=True, exist_ok=False)
        con = duckdb.connect()
        prediction_file = str(prediction_root / "oos_prediction.parquet")
        inventory_files = str(later_canonical_root / "inventory_daily" / "*.parquet")
        later_observation = con.execute("SELECT max(business_date) FROM read_parquet(?)", [inventory_files]).fetchone()[0]
        records = con.execute("""WITH predictions AS (
                SELECT * FROM read_parquet(?)
            ), daily AS (
                SELECT p.prediction_id,p.prediction_set_id,p.predicted_oos_date,p.prediction_date,p.is_top_10,
                       i.business_date,
                       CASE WHEN i.on_hand_quantity=0 AND i.assorted AND i.replenishment_enabled THEN true ELSE false END observed_oos
                FROM (SELECT x.*,? prediction_set_id FROM predictions x) p
                LEFT JOIN read_parquet(?) i ON i.location_id=p.store_id AND i.product_id=p.product_id
                    AND i.business_date BETWEEN p.prediction_date+1 AND p.prediction_date+28
            )
            SELECT prediction_id,prediction_set_id,predicted_oos_date,max(prediction_date)+28 horizon_end,
                   min(business_date) FILTER(WHERE observed_oos) actual_first_oos_date,
                   coalesce(bool_or(observed_oos),false) oos_outcome,is_top_10,
                   count(DISTINCT business_date)=28 complete_horizon
            FROM daily GROUP BY prediction_id,prediction_set_id,predicted_oos_date,is_top_10
            ORDER BY prediction_id""", [prediction_file, prediction_manifest["prediction_set_id"], inventory_files]).fetchall()
        rows = []
        for prediction_id, prediction_set_id, predicted, horizon_end, actual, outcome, displayed, complete in records:
            matured = later_observation is not None and later_observation >= horizon_end
            evaluable = bool(complete and matured)
            error = (predicted - actual).days if evaluable and actual is not None else None
            rows.append({"prediction_id": prediction_id, "prediction_set_id": prediction_set_id, "predicted_oos_date": predicted, "actual_first_oos_date": actual if evaluable else None, "oos_outcome": bool(outcome) if evaluable else None, "lead_time_error_days": error, "absolute_lead_time_error_days": abs(error) if error is not None else None, "was_displayed": displayed, "evaluable": evaluable, "reason_code": None if evaluable else "incomplete_observable_horizon"})
        table = pa.Table.from_pylist(rows, schema=SCHEMA)
        output = stage / "oos_evaluation.parquet"
        pq.write_table(table, output, compression="zstd")
        displayed = [row for row in rows if row["was_displayed"] and row["evaluable"]]
        precision = sum(bool(row["oos_outcome"]) for row in displayed) / len(displayed) if displayed else None
        manifest = {"evaluation_id": evaluation_id, **identity, "evaluation_source_release_set_id": canonical_manifest.get("source_release_set_id"), "evaluable_displayed_count": len(displayed), "precision_at_10": precision, "files": [{"path": output.name, "bytes": output.stat().st_size, "sha256": sha256_file(output), "rows": table.num_rows}]}
        (stage / "manifest.json").write_bytes(canonical_json(manifest))
        published.parent.mkdir(parents=True, exist_ok=True)
        os.rename(stage, published)
        return published
    finally:
        run_root = data_root.resolve() / "staging" / run_id
        if run_root.exists(): shutil.rmtree(run_root)
