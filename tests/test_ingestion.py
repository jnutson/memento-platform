import json
from pathlib import Path

import duckdb
import pytest

from memento.models import IngestionFailure
from memento.orchestrator import ingest


TABLES = {"calendar_day","location","product","sales_daily","inventory_daily","demand_forecast_weekly"}


def test_valid_release_publishes_six_queryable_tables_and_replays(release_manifest: Path, tmp_path: Path):
    data_root = tmp_path / "data"
    published = ingest(release_manifest, data_root=data_root, classification="synthetic")
    manifest = json.loads((published / "manifest.json").read_text())
    assert set(manifest["dataset_mapping"].values()) == TABLES
    assert {f["path"].split("/")[0] for f in manifest["files"]} == TABLES
    assert all(r["severity"] in {"PASS", "WARN"} for r in manifest["validation_results"])
    assert any(r["rule_id"] == "CAN_SCHEMA_EXACT" for r in manifest["validation_results"])
    con = duckdb.connect()
    for table in TABLES:
        assert con.execute("SELECT count(*) FROM read_parquet(?)", [str(published/table/"*.parquet")]).fetchone()[0] > 0
        repetitions = con.execute("SELECT DISTINCT repetition_type FROM parquet_schema(?) WHERE name NOT IN ('duckdb_schema','schema')", [str(published/table/"part-00000.parquet")]).fetchall()
        assert repetitions == [("REQUIRED",)]
    before = (published / "manifest.json").stat().st_mtime_ns
    assert ingest(release_manifest, data_root=data_root, classification="synthetic") == published
    assert (published / "manifest.json").stat().st_mtime_ns == before
    assert not any((data_root / "staging").iterdir())


def test_hash_failure_publishes_nothing(release_manifest: Path, tmp_path: Path):
    data = json.loads(release_manifest.read_text())
    data["files"][0]["sha256"] = "0" * 64
    release_manifest.write_text(json.dumps(data))
    with pytest.raises(IngestionFailure, match="source_validation"):
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")
    assert not (tmp_path/"data"/"canonical").exists()


def test_undeclared_file_publishes_nothing(release_manifest: Path, tmp_path: Path):
    source = release_manifest.parent / "store_dim" / "part-00000.parquet"
    (source.parent / "undeclared.parquet").write_bytes(source.read_bytes())
    with pytest.raises(IngestionFailure, match="source_validation"):
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")
    assert not (tmp_path/"data"/"canonical").exists()


def test_canonical_reference_failure_is_not_published(release_manifest: Path, tmp_path: Path, monkeypatch):
    import memento.orchestrator as orchestrator

    original = orchestrator.canonicalize

    def corrupt_candidate(con, inventory, root):
        original(con, inventory, root)
        path = root / "sales_daily" / "part-00000.parquet"
        replacement = root / "sales_daily" / "replacement.parquet"
        source = str(path).replace("'", "''")
        target = str(replacement).replace("'", "''")
        con.execute(f"COPY (SELECT * REPLACE ('loc_'||repeat('0',64) AS location_id) FROM read_parquet('{source}')) TO '{target}' (FORMAT PARQUET)")
        replacement.replace(path)

    monkeypatch.setattr(orchestrator, "canonicalize", corrupt_candidate)
    with pytest.raises(IngestionFailure, match="canonical_validation"):
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")
    assert not (tmp_path/"data"/"canonical").exists()
