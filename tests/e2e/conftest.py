from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest


RELEASE_ID = "437b6da3ad31abe0-20270130T120000Z"
AS_OF = "2027-01-30T12:00:00Z"
CONFIGURATION_HASH = "a" * 64
SCHEMA_CHECKSUM = "0" * 64
CONTRACT_VERSIONS = {
    "product": "miro-oos-product-v1.6.0",
    "metrics": "miro-oos-metrics-v1.6.0",
    "data_scope": "miro-oos-data-scope-v1.6.0",
    "glossary": "memento-glossary-v1.3.0",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(dataset_root: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        relative_path = path.relative_to(dataset_root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(bytes.fromhex(_digest(path)))
    return digest.hexdigest()


def _write_query(
    connection: duckdb.DuckDBPyConnection,
    package_root: Path,
    dataset_name: str,
    query: str,
    *,
    partitioned: bool = False,
) -> Path:
    dataset_root = package_root / dataset_name
    if partitioned:
        output_path = dataset_root / "wm_yr_wk_nbr=202649" / "part-shard-0000.parquet"
    else:
        output_path = dataset_root / "part-00000.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    connection.execute(
        f"COPY ({query}) TO '{output_path.as_posix()}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return output_path


def _dataset_entry(
    package_root: Path,
    dataset_name: str,
    path: Path,
    primary_key: list[str],
    *,
    partitioned: bool = False,
) -> dict[str, object]:
    dataset_root = package_root / dataset_name
    with duckdb.connect() as connection:
        row_count = connection.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(path)]
        ).fetchone()[0]
    return {
        "classification": "observable",
        "compression": "zstd",
        "dataset_name": dataset_name,
        "duplicate_check": "passed",
        "file_count": 1,
        "maximum_date": None,
        "minimum_date": None,
        "null_check": "passed",
        "parquet_writer_version": "duckdb-test-fixture",
        "partition_columns": ["wm_yr_wk_nbr", "store_shard"] if partitioned else [],
        "primary_key": primary_key,
        "referential_integrity": "passed",
        "relative_output_path": dataset_name,
        "row_count": row_count,
        "schema_checksum": SCHEMA_CHECKSUM,
        "schema_version": "1.0.0",
        "sha256": _tree_hash(dataset_root, [path]),
    }


def _write_walmart_package(release_root: Path) -> tuple[Path, dict[str, object]]:
    package_root = release_root / "packages" / "walmart"
    connection = duckdb.connect()
    try:
        queries = {
            "calendar_dim": """
                SELECT d::DATE cal_dt, 'US'::VARCHAR geo_region_cd,
                    day(d)::INTEGER cal_day_nbr, isodow(d)::INTEGER cal_wk_day_nbr,
                    dayname(d)::VARCHAR cal_wk_day_nm, month(d)::INTEGER cal_mth_nbr,
                    monthname(d)::VARCHAR cal_mth_nm, quarter(d)::INTEGER cal_qtr_nbr,
                    year(d)::INTEGER cal_full_yr_nbr, dayofyear(d)::INTEGER wm_day_nbr,
                    week(d)::INTEGER wm_week_nbr, month(d)::INTEGER wm_mth_nbr,
                    quarter(d)::INTEGER wm_qtr_nbr, isoyear(d)::INTEGER wm_yr_nbr,
                    month(d)::INTEGER fiscal_mth_nbr, quarter(d)::INTEGER fiscal_qtr_nbr,
                    isoyear(d)::INTEGER fiscal_full_yr_nbr,
                    (isoyear(d) * 100 + week(d))::INTEGER wm_yr_wk_nbr,
                    (d - INTERVAL 364 DAY)::DATE ly_cal_dt,
                    (d - INTERVAL 364 DAY)::DATE ly_comp_visit_dt,
                    (isoyear(d - INTERVAL 364 DAY) * 100 + week(d - INTERVAL 364 DAY))::INTEGER
                        ly_comp_yr_wk_nbr
                FROM range(DATE '2026-12-05', DATE '2027-02-27', INTERVAL 1 DAY) dates(d)
            """,
            "store_dim": """
                SELECT 10::INTEGER store_nbr, 'US'::VARCHAR geo_region_cd,
                    0::INTEGER op_cmpny_cd, 'Demo Store'::VARCHAR store_nm,
                    'SC'::VARCHAR store_type_cd, 'Supercenter'::VARCHAR store_type_desc,
                    'O'::VARCHAR open_status_cd, 'Open'::VARCHAR open_status_desc,
                    'Los Angeles'::VARCHAR city_nm, 'Los Angeles'::VARCHAR cnty_nm,
                    'CA'::VARCHAR state_prov_cd, 'California'::VARCHAR st_prov_nm,
                    '90001'::VARCHAR postal_cd, 34.0::DOUBLE lat_dgr,
                    -118.0::DOUBLE long_dgr, 1::INTEGER region_nbr,
                    'West'::VARCHAR region_nm, 2::INTEGER market_nbr,
                    'Demo'::VARCHAR market_nm, 'PST'::VARCHAR tz_cd,
                    'America/Los_Angeles'::VARCHAR tz_nm
            """,
            "omni_item_dimensions": """
                SELECT 0::INTEGER op_cmpny_cd, 100::BIGINT wm_item_nbr,
                    'Demo Item'::VARCHAR item_nm, 'Synthetic demo item'::VARCHAR item_desc,
                    '000000000100'::VARCHAR upc_nbr, 'BRAND_A'::VARCHAR brand_nm,
                    1::INTEGER omni_dept_nbr, 'Dept'::VARCHAR omni_dept_desc,
                    2::INTEGER omni_catg_nbr, 'Category'::VARCHAR omni_catg_desc,
                    3::INTEGER omni_subcatg_nbr, 'Subcategory'::VARCHAR omni_subcatg_desc,
                    4::INTEGER fineline_nbr, 'Fineline'::VARCHAR fineline_desc,
                    'ALL'::VARCHAR season_cd, 'A'::VARCHAR item_status_cd,
                    DATE '2025-01-01' item_effective_dt, true::BOOLEAN item_repl_ind,
                    'EA'::VARCHAR retail_uom_cd, 10.0::DOUBLE base_unit_rtl_amt,
                    'ST'::VARCHAR item_type_cd, 'R'::VARCHAR repl_type_cd
            """,
            "store_sales": """
                SELECT d::DATE bus_dt, 'US'::VARCHAR geo_region_cd, 0::INTEGER rpt_cd,
                    10::INTEGER store_nbr, 'BIS'::VARCHAR svc_chnl_nm,
                    100::BIGINT wm_item_nbr, 0::INTEGER op_cmpny_cd,
                    (isoyear(d) * 100 + week(d))::INTEGER wm_yr_wk_nbr,
                    1::INTEGER ty_qty, 10.0::DOUBLE ty_sales_amt,
                    1::INTEGER ly_qty, 10.0::DOUBLE ly_sales_amt
                FROM range(DATE '2026-12-05', DATE '2027-01-30', INTERVAL 1 DAY) dates(d)
            """,
            "store_invt": """
                SELECT d::DATE bus_dt, 0::INTEGER op_cmpny_cd, 10::INTEGER store_nbr,
                    100::BIGINT wm_item_nbr, 'US'::VARCHAR geo_region_cd,
                    (isoyear(d) * 100 + week(d))::INTEGER wm_yr_wk_nbr,
                    'USD'::VARCHAR crncy_cd, '1'::VARCHAR mds_fam_id,
                    (CASE WHEN d = DATE '2027-01-29' THEN 2 ELSE 100 END)::INTEGER ty_on_hand_qty,
                    100::INTEGER ly_on_hand_qty,
                    (CASE WHEN d = DATE '2027-01-29' THEN 20 ELSE 1000 END)::DOUBLE ty_on_hand_rtl_amt,
                    1000.0::DOUBLE ly_on_hand_rtl_amt, 5::INTEGER ty_on_order_qty,
                    0::INTEGER ly_on_order_qty, 0::INTEGER ty_in_transit_qty,
                    0::INTEGER ly_in_transit_qty, 0::INTEGER ty_rcpt_qty,
                    0::INTEGER ly_rcpt_qty, 100::INTEGER ty_max_shelf_qty,
                    100::INTEGER ly_max_shelf_qty, true::BOOLEAN ty_traited_ind,
                    true::BOOLEAN ly_traited_ind, true::BOOLEAN ty_repl_ind,
                    true::BOOLEAN ly_repl_ind, 10.0::DOUBLE curr_store_unit_rtl_amt
                FROM range(DATE '2026-12-05', DATE '2027-01-30', INTERVAL 1 DAY) dates(d)
            """,
            "long_rng_store_dmd_frcst": """
                SELECT DISTINCT 202648::INTEGER fcst_wm_yr_wk_nbr,
                    'US'::VARCHAR geo_region_cd, 0::INTEGER op_cmpny_cd,
                    10::INTEGER store_nbr, 100::BIGINT wm_item_nbr,
                    (isoyear(d) * 100 + week(d))::INTEGER wm_yr_wk_nbr,
                    7.0::DOUBLE final_fcst_each_qty
                FROM range(DATE '2026-12-05', DATE '2027-02-27', INTERVAL 1 DAY) dates(d)
            """,
        }
        primary_keys = {
            "calendar_dim": ["cal_dt", "geo_region_cd"],
            "store_dim": ["store_nbr"],
            "omni_item_dimensions": ["op_cmpny_cd", "wm_item_nbr"],
            "store_sales": ["bus_dt", "geo_region_cd", "rpt_cd", "store_nbr", "svc_chnl_nm", "wm_item_nbr"],
            "store_invt": ["bus_dt", "op_cmpny_cd", "store_nbr", "wm_item_nbr"],
            "long_rng_store_dmd_frcst": ["fcst_wm_yr_wk_nbr", "geo_region_cd", "op_cmpny_cd", "store_nbr", "wm_item_nbr", "wm_yr_wk_nbr"],
        }
        partitioned_names = {"store_sales", "store_invt", "long_rng_store_dmd_frcst"}
        files: dict[str, Path] = {}
        datasets: list[dict[str, object]] = []
        for name, query in queries.items():
            path = _write_query(connection, package_root, name, query, partitioned=name in partitioned_names)
            files[name] = path
            datasets.append(_dataset_entry(package_root, name, path, primary_keys[name], partitioned=name in partitioned_names))
    finally:
        connection.close()

    manifest = {
        "as_of": AS_OF,
        "classification": "synthetic",
        "configuration_hash": CONFIGURATION_HASH,
        "contract_versions": CONTRACT_VERSIONS,
        "dataset_type": "observable",
        "datasets": datasets,
        "files": [
            {"bytes": path.stat().st_size, "path": path.relative_to(package_root).as_posix(), "sha256": _digest(path)}
            for path in sorted(files.values())
        ],
        "manifest_schema_version": "2.0.0",
        "release_gates": {
            "duplicates": "passed",
            "null_checks": "passed",
            "referential_integrity": "passed",
            "schema_validation": "passed",
        },
        "release_id": RELEASE_ID,
    }
    manifest_path = package_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return manifest_path, manifest


def _write_extension_package(release_root: Path, source_manifest: dict[str, object]) -> tuple[Path, dict[str, object]]:
    package_root = release_root / "packages" / "extension"
    connection = duckdb.connect()
    try:
        queries = {
            "dim_item": """
                SELECT 'MIRO_TOYS'::VARCHAR company_id,
                    'MIRO-SPARK-001'::VARCHAR company_item_id,
                    'Demo Item'::VARCHAR company_item_name,
                    'MIRO_SPARK'::VARCHAR display_brand_id,
                    0::TINYINT op_cmpny_cd, 100::BIGINT wm_item_nbr,
                    DATE '2025-01-01' effective_from, NULL::DATE effective_to
            """,
            "retailer_replenishment_commitment": """
                SELECT 'PO-DEMO-001'::VARCHAR retailer_order_id,
                    1::INTEGER order_line_nbr, 1::INTEGER event_version,
                    10::INTEGER store_nbr, 0::TINYINT op_cmpny_cd,
                    100::BIGINT wm_item_nbr, 5::INTEGER ordered_qty,
                    0::INTEGER invoiced_qty, 0::INTEGER received_qty,
                    TIMESTAMPTZ '2027-01-20 12:00:00+00' order_created_at,
                    NULL::TIMESTAMPTZ approved_to_ship_at,
                    NULL::TIMESTAMPTZ dc_invoiced_at,
                    DATE '2027-02-05' expected_store_receipt_date,
                    NULL::TIMESTAMPTZ actual_store_receipt_at,
                    'ordered'::VARCHAR status_cd,
                    TIMESTAMPTZ '2027-01-20 12:00:00+00' known_at
            """,
            "item_reaction_constraint": """
                SELECT 'MIRO_TOYS'::VARCHAR company_id,
                    'brand'::VARCHAR item_scope_type_cd,
                    'MIRO_SPARK'::VARCHAR item_scope_id,
                    10::INTEGER minimum_reaction_days,
                    DATE '2025-01-01' effective_from,
                    NULL::DATE effective_to
            """,
        }
        primary_keys = {
            "dim_item": ["company_id", "company_item_id"],
            "retailer_replenishment_commitment": ["retailer_order_id", "order_line_nbr", "event_version"],
            "item_reaction_constraint": ["company_id", "item_scope_type_cd", "item_scope_id", "effective_from"],
        }
        datasets: list[dict[str, object]] = []
        for name, query in queries.items():
            path = _write_query(connection, package_root, name, query)
            row_count = connection.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
            datasets.append({
                "checks": {"duplicates": "passed", "null_checks": "passed", "schema_validation": "passed"},
                "file_count": 1,
                "dataset_name": name,
                "relative_output_path": name,
                "primary_key": primary_keys[name],
                "row_count": row_count,
                "schema_checksum": SCHEMA_CHECKSUM,
                "sha256": _tree_hash(package_root / name, [path]),
            })
    finally:
        connection.close()

    manifest = {
        "checks": {"three_datasets_only": True, "cutoff_safe": True},
        "configuration_hash": CONFIGURATION_HASH,
        "contract_versions": CONTRACT_VERSIONS,
        "datasets": datasets,
        "manifest_schema_version": "1.0.0",
        "po_retention_days": 56,
        "release_id": RELEASE_ID,
        "source_walmart_manifest_sha256": hashlib.sha256(json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    }
    manifest_path = package_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return manifest_path, manifest


def build_attention_release_set(tmp_path: Path) -> Path:
    release_root = tmp_path / "release-set-root"
    walmart_path, walmart_manifest = _write_walmart_package(release_root)
    extension_path, _ = _write_extension_package(release_root, walmart_manifest)
    release_manifest = {
        "as_of": AS_OF,
        "configuration_hash": CONFIGURATION_HASH,
        "contract_versions": CONTRACT_VERSIONS,
        "extension_manifest": extension_path.relative_to(release_root).as_posix(),
        "extension_manifest_sha256": _digest(extension_path),
        "manifest_schema_version": "1.0.0",
        "release_id": RELEASE_ID,
        "walmart_manifest": walmart_path.relative_to(release_root).as_posix(),
        "walmart_manifest_sha256": _digest(walmart_path),
    }
    manifest_path = release_root / "release-sets" / RELEASE_ID / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(release_manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return manifest_path


@pytest.fixture
def attention_release_set_manifest(tmp_path: Path) -> Path:
    return build_attention_release_set(tmp_path)
