import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from memento.models import IngestionFailure
from memento.orchestrator import DUCKDB_MEMORY_LIMIT, _configure_analytics_connection, ingest


TABLES = {"calendar_day","location","product","sales_daily","inventory_daily","demand_forecast_weekly"}


def test_duckdb_runtime_is_memory_bounded_and_spills_inside_staging(tmp_path: Path):
    con = duckdb.connect()
    run_root = tmp_path / "data" / "staging" / "run_test"

    _configure_analytics_connection(con, run_root)

    assert DUCKDB_MEMORY_LIMIT == "2GB"
    assert con.execute("SELECT current_setting('memory_limit')").fetchone()[0] == "1.8 GiB"
    assert con.execute("SELECT current_setting('temp_directory')").fetchone()[0] == str(
        run_root / "duckdb-spill"
    )


def _rewrite_source_dataset(manifest_path: Path, dataset: str, query_template: str) -> None:
    manifest = json.loads(manifest_path.read_text())
    entry = next(item for item in manifest["files"] if item["path"].startswith(dataset + "/"))
    source = manifest_path.parent / entry["path"]
    replacement = source.with_suffix(".replacement.parquet")
    escaped_source = str(source).replace("'", "''")
    escaped_replacement = str(replacement).replace("'", "''")
    scan = f"read_parquet('{escaped_source}', hive_partitioning=false)"
    con = duckdb.connect()
    con.execute(
        f"COPY ({query_template.format(scan=scan)}) TO '{escaped_replacement}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    replacement.replace(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    entry["bytes"] = source.stat().st_size
    entry["sha256"] = digest
    descriptor = next(item for item in manifest["datasets"] if item["dataset_name"] == dataset)
    descriptor["row_count"] = con.execute(f"SELECT count(*) FROM {scan}").fetchone()[0]
    tree = hashlib.sha256()
    tree.update(source.relative_to(manifest_path.parent / dataset).as_posix().encode())
    tree.update(bytes.fromhex(digest))
    descriptor["sha256"] = tree.hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))


def test_valid_release_publishes_six_queryable_tables_and_replays(release_manifest: Path, tmp_path: Path):
    data_root = tmp_path / "data"
    published = ingest(release_manifest, data_root=data_root, classification="synthetic")
    manifest = json.loads((published / "manifest.json").read_text())
    assert set(manifest["dataset_mapping"].values()) == TABLES
    assert manifest["validation_contract_version"] == "1.1.1"
    assert {f["path"].split("/")[0] for f in manifest["files"]} == TABLES
    assert all(r["severity"] in {"PASS", "WARN"} for r in manifest["validation_results"])
    assert any(r["rule_id"] == "CAN_SCHEMA_EXACT" for r in manifest["validation_results"])
    assert any(r["rule_id"] == "CAN_SCHEMA_REQUIRED" for r in manifest["validation_results"])
    assert any(r["rule_id"] == "CAN_UPC_UNIQUE" for r in manifest["validation_results"])
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


def test_customer_classification_is_rejected_before_data_root_creation(
    release_manifest: Path, tmp_path: Path
):
    data_root = tmp_path / "data"

    with pytest.raises(IngestionFailure) as error:
        ingest(
            release_manifest,
            data_root=data_root,
            classification="confidential-customer",
        )

    assert error.value.phase == "source_validation"
    assert {result.rule_id for result in error.value.results} == {
        "SRC_TRUSTED_CLASSIFICATION"
    }
    assert not data_root.exists()


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


def test_duplicate_source_upc_is_rejected(release_manifest: Path, tmp_path: Path):
    _rewrite_source_dataset(
        release_manifest,
        "omni_item_dimensions",
        "SELECT * FROM {scan} UNION ALL SELECT * REPLACE (101::BIGINT AS wm_item_nbr) FROM {scan}",
    )

    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")

    assert "SRC_UPC_UNIQUE" in {
        result.rule_id for result in error.value.results if result.severity == "FAIL"
    }
    assert not (tmp_path/"data"/"canonical").exists()


def test_invalid_source_timezone_is_rejected(release_manifest: Path, tmp_path: Path):
    _rewrite_source_dataset(
        release_manifest,
        "store_dim",
        "SELECT * REPLACE ('Not/A_Timezone'::VARCHAR AS tz_nm) FROM {scan}",
    )

    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")

    assert "SRC_TIMEZONE_DOMAIN" in {
        result.rule_id for result in error.value.results if result.severity == "FAIL"
    }
    assert not (tmp_path/"data"/"canonical").exists()


def test_source_schema_drift_is_reported_as_validation_failure(
    release_manifest: Path, tmp_path: Path
):
    _rewrite_source_dataset(
        release_manifest,
        "store_dim",
        "SELECT * EXCLUDE (tz_nm) FROM {scan}",
    )

    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")

    assert "SRC_SCHEMA_EXACT" in {
        result.rule_id for result in error.value.results if result.severity == "FAIL"
    }
    assert not (tmp_path/"data"/"canonical").exists()


@pytest.mark.parametrize(
    ("dataset", "replacement", "rule"),
    [
        ("calendar_dim", "300::INTEGER AS cal_day_nbr", "SRC_CALENDAR_RULES"),
        ("calendar_dim", "1::INTEGER AS cal_day_nbr", "SRC_CALENDAR_RULES"),
        ("store_dim", "-1::INTEGER AS store_nbr", "SRC_LOCATION_RULES"),
        ("omni_item_dimensions", "1e20::DOUBLE AS base_unit_rtl_amt", "SRC_PRODUCT_RULES"),
        ("long_rng_store_dmd_frcst", "1e15::DOUBLE AS final_fcst_each_qty", "SRC_FORECAST_DOMAIN"),
    ],
)
def test_out_of_range_source_values_are_rejected_before_canonical_casts(
    release_manifest: Path,
    tmp_path: Path,
    dataset: str,
    replacement: str,
    rule: str,
):
    _rewrite_source_dataset(
        release_manifest,
        dataset,
        f"SELECT * REPLACE ({replacement}) FROM {{scan}}",
    )

    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")

    assert rule in {result.rule_id for result in error.value.results if result.severity == "FAIL"}
    assert not (tmp_path/"data"/"canonical").exists()


@pytest.mark.parametrize(
    ("amount", "publishes"),
    [("2.500009", True), ("2.50002", False)],
)
def test_source_money_rounding_tolerance(
    release_manifest: Path, tmp_path: Path, amount: str, publishes: bool
):
    _rewrite_source_dataset(
        release_manifest,
        "store_sales",
        f"SELECT * REPLACE ({amount}::DOUBLE AS ly_sales_amt) FROM {{scan}}",
    )

    if publishes:
        assert ingest(
            release_manifest, data_root=tmp_path / "data", classification="synthetic"
        ).is_dir()
    else:
        with pytest.raises(IngestionFailure) as error:
            ingest(
                release_manifest,
                data_root=tmp_path / "data",
                classification="synthetic",
            )
        assert "SRC_SALES_DOMAIN" in {
            result.rule_id
            for result in error.value.results
            if result.severity == "FAIL"
        }


@pytest.mark.parametrize(
    ("table", "replacement", "rule"),
    [
        ("sales_daily", "'invalid'::VARCHAR AS retail_type_code", "CAN_SALES_DOMAIN"),
        ("product", "'prd_'||repeat('0',64) AS product_id", "CAN_STABLE_ID"),
        ("location", "'Not/A_Timezone'::VARCHAR AS timezone_name", "CAN_TIMEZONE_DOMAIN"),
        ("calendar_day", "202500::INTEGER AS comparable_retail_year_week", "CAN_CALENDAR_RULES"),
    ],
)
def test_canonical_semantic_failure_is_not_published(
    release_manifest: Path,
    tmp_path: Path,
    monkeypatch,
    table: str,
    replacement: str,
    rule: str,
):
    import memento.orchestrator as orchestrator

    original = orchestrator.canonicalize

    def corrupt_candidate(con, inventory, root):
        original(con, inventory, root)
        path = root / table / "part-00000.parquet"
        replacement_path = root / table / "replacement.parquet"
        source = str(path).replace("'", "''")
        target = str(replacement_path).replace("'", "''")
        con.execute(
            f"COPY (SELECT * REPLACE ({replacement}) FROM read_parquet('{source}')) "
            f"TO '{target}' (FORMAT PARQUET)"
        )
        replacement_path.replace(path)

    monkeypatch.setattr(orchestrator, "canonicalize", corrupt_candidate)
    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")

    assert rule in {result.rule_id for result in error.value.results if result.severity == "FAIL"}
    assert not (tmp_path/"data"/"canonical").exists()


def test_duplicate_canonical_upc_is_not_published(release_manifest: Path, tmp_path: Path, monkeypatch):
    _rewrite_source_dataset(
        release_manifest,
        "omni_item_dimensions",
        "SELECT * FROM {scan} UNION ALL SELECT * REPLACE (101::BIGINT AS wm_item_nbr, '000000000101'::VARCHAR AS upc_nbr) FROM {scan}",
    )
    import memento.orchestrator as orchestrator

    original = orchestrator.canonicalize

    def corrupt_candidate(con, inventory, root):
        original(con, inventory, root)
        path = root / "product" / "part-00000.parquet"
        replacement = root / "product" / "replacement.parquet"
        source = str(path).replace("'", "''")
        target = str(replacement).replace("'", "''")
        con.execute(
            f"COPY (SELECT * REPLACE ('000000000100'::VARCHAR AS upc) FROM read_parquet('{source}')) "
            f"TO '{target}' (FORMAT PARQUET)"
        )
        replacement.replace(path)

    monkeypatch.setattr(orchestrator, "canonicalize", corrupt_candidate)
    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")

    assert "CAN_UPC_UNIQUE" in {
        result.rule_id for result in error.value.results if result.severity == "FAIL"
    }
    assert not (tmp_path/"data"/"canonical").exists()


@pytest.mark.parametrize(
    ("query", "rule"),
    [
        ("SELECT * EXCLUDE (upc) FROM read_parquet('{source}')", "CAN_SCHEMA_EXACT"),
        ("SELECT * FROM read_parquet('{source}')", "CAN_SCHEMA_REQUIRED"),
    ],
)
def test_canonical_schema_failures_are_structured_and_not_published(
    release_manifest: Path,
    tmp_path: Path,
    monkeypatch,
    query: str,
    rule: str,
):
    import memento.orchestrator as orchestrator

    original = orchestrator.canonicalize

    def corrupt_candidate(con, inventory, root):
        original(con, inventory, root)
        path = root / "product" / "part-00000.parquet"
        replacement = root / "product" / "replacement.parquet"
        source = str(path).replace("'", "''")
        target = str(replacement).replace("'", "''")
        con.execute(
            f"COPY ({query.format(source=source)}) TO '{target}' (FORMAT PARQUET)"
        )
        replacement.replace(path)

    monkeypatch.setattr(orchestrator, "canonicalize", corrupt_candidate)
    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path/"data", classification="synthetic")

    assert rule in {result.rule_id for result in error.value.results if result.severity == "FAIL"}
    assert not (tmp_path/"data"/"canonical").exists()


def test_failure_after_staging_allows_clean_retry(
    release_manifest: Path, tmp_path: Path, monkeypatch
):
    import memento.orchestrator as orchestrator

    data_root = tmp_path / "data"
    original = orchestrator.canonicalize

    def fail_after_writing_candidate(con, inventory, root):
        original(con, inventory, root)
        raise RuntimeError("injected post-staging failure")

    monkeypatch.setattr(orchestrator, "canonicalize", fail_after_writing_candidate)
    with pytest.raises(RuntimeError, match="injected post-staging failure"):
        ingest(release_manifest, data_root=data_root, classification="synthetic")

    assert not (data_root / "canonical").exists()
    assert not any((data_root / "staging").iterdir())

    monkeypatch.setattr(orchestrator, "canonicalize", original)
    published = ingest(release_manifest, data_root=data_root, classification="synthetic")

    assert (published / "manifest.json").is_file()
    assert not any((data_root / "staging").iterdir())


def test_failure_logs_and_errors_do_not_expose_source_payloads(
    release_manifest: Path, tmp_path: Path, caplog
):
    sensitive_marker = "PRIVATE-CUSTOMER-VALUE-DO-NOT-LOG"
    _rewrite_source_dataset(
        release_manifest,
        "omni_item_dimensions",
        "SELECT * REPLACE ("
        f"'{sensitive_marker}'::VARCHAR AS item_nm, "
        "-1.0::DOUBLE AS base_unit_rtl_amt) FROM {scan}",
    )

    with pytest.raises(IngestionFailure) as error:
        ingest(release_manifest, data_root=tmp_path / "data", classification="synthetic")

    assert "SRC_PRODUCT_RULES" in str(error.value)
    assert sensitive_marker not in str(error.value)
    assert sensitive_marker not in caplog.text
    quarantine = next((tmp_path / "data" / "quarantine").glob("*/validation-summary.json"))
    assert sensitive_marker not in quarantine.read_text(encoding="utf-8")


def test_ingestion_does_not_modify_source_release(release_manifest: Path, tmp_path: Path):
    source_files = sorted(
        path for path in release_manifest.parent.rglob("*") if path.is_file()
    )
    before = {
        path.relative_to(release_manifest.parent): (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in source_files
    }

    ingest(release_manifest, data_root=tmp_path / "data", classification="synthetic")

    after_files = sorted(
        path for path in release_manifest.parent.rglob("*") if path.is_file()
    )
    after = {
        path.relative_to(release_manifest.parent): (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in after_files
    }
    assert after == before
