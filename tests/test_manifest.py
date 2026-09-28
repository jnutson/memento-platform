import json
from pathlib import Path

import pytest

from memento.manifest import inspect_manifest, validate_manifest_contract
from memento.models import IngestionFailure


def test_manifest_requires_absolute_path(release_manifest: Path):
    with pytest.raises(IngestionFailure, match="SRC_PATH_EXPLICIT"):
        inspect_manifest(Path("manifest.json"), "synthetic")


def test_manifest_rejects_traversal(release_manifest: Path):
    data = json.loads(release_manifest.read_text())
    data["files"][0]["path"] = "../escape.parquet"
    release_manifest.write_text(json.dumps(data))
    with pytest.raises(IngestionFailure, match="SRC_FILE_PATH"):
        inspect_manifest(release_manifest, "synthetic")


def test_future_release_requires_trusted_synthetic_classification(release_manifest: Path):
    inventory = inspect_manifest(release_manifest, "internal")
    failed = [r.rule_id for r in validate_manifest_contract(inventory) if r.severity == "FAIL"]
    assert "SRC_FUTURE_AS_OF" in failed


def test_symlinked_input_is_rejected(release_manifest: Path):
    data = json.loads(release_manifest.read_text())
    declared = release_manifest.parent / data["files"][0]["path"]
    target = declared.with_suffix(".original")
    declared.replace(target)
    declared.symlink_to(target)
    with pytest.raises(IngestionFailure, match="SRC_FILE_REGULAR"):
        inspect_manifest(release_manifest, "synthetic")
