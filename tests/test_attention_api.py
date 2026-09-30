from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from memento.api import API_CONTRACT_VERSION, create_app
from memento.prediction import run_predictions

from test_prediction_pipeline import _canonical_fixture


def _api_fixture(tmp_path: Path) -> TestClient:
    (tmp_path / "source").mkdir()
    canonical_source = _canonical_fixture(tmp_path / "source")
    data_root = tmp_path / "data"
    canonical_target = data_root / "canonical" / "mds_fixture"
    canonical_target.parent.mkdir(parents=True)
    shutil.copytree(canonical_source, canonical_target)
    run_predictions(canonical_source, data_root=data_root)
    return TestClient(create_app(data_root))


def test_attention_queue_and_detail_preserve_published_contract(tmp_path: Path):
    client = _api_fixture(tmp_path)

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["api_contract_version"] == API_CONTRACT_VERSION

    queue_response = client.get("/v1/attention")
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert queue["api_contract_version"] == API_CONTRACT_VERSION
    assert queue["summary"] == {
        "eligible_candidate_count": 1,
        "displayed_prediction_count": 1,
        "estimated_lost_units": "26.000000",
        "estimated_lost_sales_amount": "260.00",
    }
    prediction = queue["predictions"][0]
    assert prediction["rank_position"] == 1
    assert prediction["identity"] == {
        "item_name": "Miro Spark One",
        "company_item_id": "MIRO-SPARK-001",
        "source_product_id": "100",
        "store_name": "Synthetic Store 10",
        "source_location_id": "10",
    }
    assert isinstance(prediction["rank_score"], str)

    detail_response = client.get(f"/v1/attention/{prediction['prediction_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert len(detail["evidence"]) == 84
    assert {row["path"] for row in detail["evidence"]} == {"low", "base", "high"}
    assert detail["prediction"]["prediction_id"] == prediction["prediction_id"]
    assert detail["prediction"]["starting_on_hand_units"] == "2.000000"
    assert detail["scheduled_inbound"] == []


def test_attention_api_rejects_invalid_identity_with_versioned_error(tmp_path: Path):
    client = _api_fixture(tmp_path)
    response = client.get("/v1/attention/not-a-prediction")
    assert response.status_code == 422
    assert response.json() == {
        "api_contract_version": API_CONTRACT_VERSION,
        "code": "invalid_prediction_id",
        "message": "The prediction identifier is invalid.",
    }


def test_attention_api_rejects_manifest_bound_canonical_mismatch(tmp_path: Path):
    client = _api_fixture(tmp_path)
    data_root = tmp_path / "data"
    manifest_path = data_root / "canonical" / "mds_fixture" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["dataset_id"] = "mds_other"
    manifest_path.write_text(json.dumps(manifest))

    response = client.get("/v1/attention")
    assert response.status_code == 503
    assert response.json()["code"] == "release_integrity_error"
