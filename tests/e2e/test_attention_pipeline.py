from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memento.api import create_app
from memento.orchestrator import ingest
from memento.prediction import run_predictions


@pytest.mark.e2e
def test_synthetic_release_reaches_attention_api(attention_release_set_manifest: Path, tmp_path: Path) -> None:
    data_root = tmp_path / "runtime-data"

    canonical_path = ingest(attention_release_set_manifest, data_root=data_root, classification="synthetic")
    prediction_path = run_predictions(canonical_path, data_root=data_root)

    canonical_manifest = json.loads((canonical_path / "manifest.json").read_text(encoding="utf-8"))
    prediction_manifest = json.loads((prediction_path / "manifest.json").read_text(encoding="utf-8"))
    client = TestClient(create_app(data_root))

    health = client.get("/healthz").json()
    assert health["status"] == "ok"
    assert health["prediction_set_id"] == prediction_manifest["prediction_set_id"]
    queue_response = client.get("/v1/attention")
    assert queue_response.status_code == 200
    queue = queue_response.json()

    assert queue["run"]["canonical_dataset_id"] == canonical_manifest["dataset_id"]
    assert queue["run"]["prediction_set_id"] == prediction_manifest["prediction_set_id"]
    assert queue["run"]["source_release_set_id"] == canonical_manifest["source_release_set_id"]
    assert queue["summary"]["eligible_candidate_count"] == 1
    assert queue["summary"]["displayed_prediction_count"] == 1
    assert [item["rank_position"] for item in queue["predictions"]] == [1]

    item = queue["predictions"][0]
    assert item["identity"] == {
        "item_name": "Demo Item",
        "company_item_id": "MIRO-SPARK-001",
        "source_product_id": "100",
        "store_name": "Demo Store",
        "source_location_id": "10",
    }
    assert item["estimated_lost_units"].count(".") == 1

    detail_response = client.get(f"/v1/attention/{item['prediction_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["prediction"]["prediction_id"] == item["prediction_id"]
    assert len(detail["evidence"]) == 84
    assert sum(row["path"] == "low" for row in detail["evidence"]) == 28
    assert sum(row["path"] == "base" for row in detail["evidence"]) == 28
    assert sum(row["path"] == "high" for row in detail["evidence"]) == 28
    assert detail["scheduled_inbound"] == [
        {"expected_store_receipt_date": "2027-02-05", "scheduled_inbound_units": "5.000000"}
    ]

    repeated_canonical = ingest(attention_release_set_manifest, data_root=data_root, classification="synthetic")
    repeated_prediction = run_predictions(repeated_canonical, data_root=data_root)
    assert repeated_canonical == canonical_path
    assert repeated_prediction == prediction_path
    assert client.get("/v1/attention").json() == queue
