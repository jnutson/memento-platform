from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memento.api import (
    API_CONTRACT_VERSION,
    EvidenceRow,
    _validate_queue_release,
    _validated_evidence,
    create_app,
)
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

    non_hex = client.get(f"/v1/attention/oos_{'z' * 64}")
    assert non_hex.status_code == 422
    assert non_hex.json()["code"] == "invalid_prediction_id"


def test_attention_api_rejects_non_contiguous_or_duplicate_queue_rows():
    manifest = {"candidate_count": 2, "display_count": 2}
    rows = [
        {"prediction_id": f"oos_{'a' * 64}", "rank_position": 1},
        {"prediction_id": f"oos_{'b' * 64}", "rank_position": 1},
    ]
    with pytest.raises(ValueError, match="ranks"):
        _validate_queue_release(manifest, rows)

    rows[1]["rank_position"] = 2
    rows[1]["prediction_id"] = rows[0]["prediction_id"]
    with pytest.raises(ValueError, match="identities"):
        _validate_queue_release(manifest, rows)


def test_attention_api_rejects_incomplete_or_mismatched_evidence():
    prediction_id = f"oos_{'a' * 64}"
    prediction_date = date(2027, 1, 29)
    rows = [
        EvidenceRow(
            prediction_id=prediction_id,
            projection_date=prediction_date + timedelta(days=offset),
            path=path,
            demand_units="1",
            scheduled_inbound_units="0",
            opening_units="1",
            available_units="1",
            fulfilled_units="1",
            lost_units="0",
            projected_ending_on_hand_units="0",
        )
        for path in ("low", "base", "high")
        for offset in range(1, 29)
    ]
    prediction = {"prediction_id": prediction_id, "prediction_date": prediction_date}
    assert set(_validated_evidence(prediction, rows)) == {"low", "base", "high"}

    rows[-1] = rows[-1].model_copy(update={"projection_date": rows[-2].projection_date})
    with pytest.raises(ValueError, match="complete 28-day paths"):
        _validated_evidence(prediction, rows)


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
