import json
from pathlib import Path

import duckdb

from memento.orchestrator import ingest


TABLES = {"calendar_day", "location", "product", "sales_daily", "inventory_daily", "demand_forecast_weekly", "company_item", "replenishment_commitment", "reaction_constraint"}


def test_release_set_publishes_nine_atomic_canonical_tables(release_set_manifest: Path, tmp_path: Path):
    output = ingest(release_set_manifest, data_root=tmp_path / "data", classification="synthetic")
    manifest = json.loads((output / "manifest.json").read_text())
    assert set(manifest["dataset_mapping"].values()) == TABLES
    assert manifest["source_release_set_manifest_sha256"]
    assert set(manifest["source_manifests"]) == {"walmart_sha256", "extension_sha256"}
    con = duckdb.connect()
    for table in TABLES:
        assert con.execute("SELECT count(*) FROM read_parquet(?)", [str(output / table / "*.parquet")]).fetchone()[0] > 0
    before = (output / "manifest.json").read_bytes()
    assert ingest(release_set_manifest, data_root=tmp_path / "data", classification="synthetic") == output
    assert (output / "manifest.json").read_bytes() == before
