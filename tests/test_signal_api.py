from pathlib import Path
import shutil
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from memento.api import SIGNAL_API_CONTRACT_VERSION, SignalDetailRow, SignalEvidenceRow, _validate_signal_queue_release, _validated_signal_evidence, create_app
from memento.signals import run_signals
from test_prediction_pipeline import _canonical_fixture


def test_signal_api_returns_immutable_rank_and_type_specific_detail(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    canonical = _canonical_fixture(source)
    data_root = tmp_path / "data"
    target = data_root / "canonical" / "mds_fixture"
    target.parent.mkdir(parents=True)
    shutil.copytree(canonical, target)
    run_signals(canonical, data_root=data_root, annual_carrying_cost_rate=Decimal("0.20"), carrying_rate_version="synthetic-test-rate-v1")
    client = TestClient(create_app(data_root))

    response = client.get("/v1/signals")
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_contract_version"] == SIGNAL_API_CONTRACT_VERSION
    assert len(payload["signals"]) == 1
    signal = payload["signals"][0]
    assert signal["signal_type"] == "availability"
    assert signal["overall_rank_position"] == 1
    assert signal["estimated_contribution_impact_amount"] == "156.00"

    filtered = client.get("/v1/signals", params={"signal_type": "availability"}).json()
    assert filtered["signals"][0]["overall_rank_position"] == 1
    detail = client.get(f"/v1/signals/{signal['signal_id']}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert len(detail_payload["evidence"]) == 84
    detail_model = SignalDetailRow.model_validate(detail_payload["signal"])
    evidence_models = [SignalEvidenceRow.model_validate(row) for row in detail_payload["evidence"]]
    with pytest.raises(ValueError, match="complete 28-day paths"):
        _validated_signal_evidence(detail_model, evidence_models[:-1])


def test_signal_api_rejects_invalid_identifier(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/v1/signals/not-a-signal")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_signal_id"
    assert response.json()["api_contract_version"] == SIGNAL_API_CONTRACT_VERSION

    invalid_filter = client.get("/v1/signals", params={"signal_type": "other"})
    assert invalid_filter.status_code == 422
    assert invalid_filter.json()["api_contract_version"] == SIGNAL_API_CONTRACT_VERSION


def test_signal_queue_integrity_rejects_duplicate_overall_ranks():
    manifest = {
        "candidate_count": 2,
        "display_count": 2,
        "candidate_counts_by_type": {"availability": 1, "demand_momentum": 1, "inventory_imbalance": 0},
    }
    rows = [
        {"signal_id": f"sig_{'a' * 64}", "signal_type": "availability", "overall_rank_position": 1},
        {"signal_id": f"sig_{'b' * 64}", "signal_type": "demand_momentum", "overall_rank_position": 1},
    ]
    with pytest.raises(ValueError, match="unique and ordered"):
        _validate_signal_queue_release(manifest, rows, None)
