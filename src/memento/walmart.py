from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .models import SourceInventory, ValidationResult


ADAPTER_ID = "walmart-observable-release-v1"
ADAPTER_VERSION = "1.0.0"
TRANSFORMATION_VERSION = "1.0.0"
VALIDATION_VERSION = "1.0.0"
RETAIL_TYPE_MAP = {0: "regular", 7: "rollback", 8: "clearance"}


def map_retail_type(value: int) -> str:
    try:
        return RETAIL_TYPE_MAP[value]
    except KeyError as exc:
        raise ValueError("unsupported Walmart rpt_cd") from exc

SOURCE_COLUMNS = {
    "calendar_dim": ["cal_dt","geo_region_cd","cal_day_nbr","cal_wk_day_nbr","cal_wk_day_nm","cal_mth_nbr","cal_mth_nm","cal_qtr_nbr","cal_full_yr_nbr","wm_day_nbr","wm_week_nbr","wm_mth_nbr","wm_qtr_nbr","wm_yr_nbr","fiscal_mth_nbr","fiscal_qtr_nbr","fiscal_full_yr_nbr","wm_yr_wk_nbr","ly_cal_dt","ly_comp_visit_dt","ly_comp_yr_wk_nbr"],
    "store_dim": ["store_nbr","geo_region_cd","op_cmpny_cd","store_nm","store_type_cd","store_type_desc","open_status_cd","open_status_desc","city_nm","cnty_nm","state_prov_cd","st_prov_nm","postal_cd","lat_dgr","long_dgr","region_nbr","region_nm","market_nbr","market_nm","tz_cd","tz_nm"],
    "omni_item_dimensions": ["op_cmpny_cd","wm_item_nbr","item_nm","item_desc","upc_nbr","brand_nm","omni_dept_nbr","omni_dept_desc","omni_catg_nbr","omni_catg_desc","omni_subcatg_nbr","omni_subcatg_desc","fineline_nbr","fineline_desc","season_cd","item_status_cd","item_effective_dt","item_repl_ind","retail_uom_cd","base_unit_rtl_amt","item_type_cd","repl_type_cd"],
    "store_sales": ["bus_dt","geo_region_cd","rpt_cd","store_nbr","svc_chnl_nm","wm_item_nbr","op_cmpny_cd","wm_yr_wk_nbr","ty_qty","ty_sales_amt","ly_qty","ly_sales_amt"],
    "store_invt": ["bus_dt","op_cmpny_cd","store_nbr","wm_item_nbr","geo_region_cd","wm_yr_wk_nbr","crncy_cd","mds_fam_id","ty_on_hand_qty","ly_on_hand_qty","ty_on_hand_rtl_amt","ly_on_hand_rtl_amt","ty_on_order_qty","ly_on_order_qty","ty_in_transit_qty","ly_in_transit_qty","ty_rcpt_qty","ly_rcpt_qty","ty_max_shelf_qty","ly_max_shelf_qty","ty_traited_ind","ly_traited_ind","ty_repl_ind","ly_repl_ind","curr_store_unit_rtl_amt"],
    "long_rng_store_dmd_frcst": ["fcst_wm_yr_wk_nbr","geo_region_cd","op_cmpny_cd","store_nbr","wm_item_nbr","wm_yr_wk_nbr","final_fcst_each_qty"],
}

SOURCE_TYPES = {
    "calendar_dim": ["DATE","VARCHAR","TINYINT","TINYINT","VARCHAR","TINYINT","VARCHAR","TINYINT","SMALLINT","SMALLINT","TINYINT","TINYINT","TINYINT","SMALLINT","TINYINT","TINYINT","SMALLINT","INTEGER","DATE","DATE","INTEGER"],
    "store_dim": ["INTEGER","VARCHAR","TINYINT","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","DOUBLE","DOUBLE","SMALLINT","VARCHAR","SMALLINT","VARCHAR","VARCHAR","VARCHAR"],
    "omni_item_dimensions": ["TINYINT","BIGINT","VARCHAR","VARCHAR","VARCHAR","VARCHAR","SMALLINT","VARCHAR","SMALLINT","VARCHAR","SMALLINT","VARCHAR","SMALLINT","VARCHAR","VARCHAR","VARCHAR","DATE","BOOLEAN","VARCHAR","DOUBLE","VARCHAR","VARCHAR"],
    "store_sales": ["DATE","VARCHAR","TINYINT","INTEGER","VARCHAR","BIGINT","TINYINT","INTEGER","INTEGER","DOUBLE","INTEGER","DOUBLE"],
    "store_invt": ["DATE","TINYINT","INTEGER","BIGINT","VARCHAR","INTEGER","VARCHAR","VARCHAR","INTEGER","INTEGER","DOUBLE","DOUBLE","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","BOOLEAN","BOOLEAN","BOOLEAN","BOOLEAN","DOUBLE"],
    "long_rng_store_dmd_frcst": ["INTEGER","VARCHAR","TINYINT","INTEGER","BIGINT","INTEGER","DOUBLE"],
}

# Retain the already-published V1 fixture/legacy observable contract while accepting
# the narrower PSP physical integer widths used by the Miro Brand A releases. These
# are two pinned schemas, not general implicit numeric coercion.
LEGACY_SOURCE_TYPES = {
    "calendar_dim": ["DATE","VARCHAR","INTEGER","INTEGER","VARCHAR","INTEGER","VARCHAR","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","DATE","DATE","INTEGER"],
    "store_dim": ["INTEGER","VARCHAR","INTEGER","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","VARCHAR","DOUBLE","DOUBLE","INTEGER","VARCHAR","INTEGER","VARCHAR","VARCHAR","VARCHAR"],
    "omni_item_dimensions": ["INTEGER","BIGINT","VARCHAR","VARCHAR","VARCHAR","VARCHAR","INTEGER","VARCHAR","INTEGER","VARCHAR","INTEGER","VARCHAR","INTEGER","VARCHAR","VARCHAR","VARCHAR","DATE","BOOLEAN","VARCHAR","DOUBLE","VARCHAR","VARCHAR"],
    "store_sales": ["DATE","VARCHAR","INTEGER","INTEGER","VARCHAR","BIGINT","INTEGER","INTEGER","INTEGER","DOUBLE","INTEGER","DOUBLE"],
    "store_invt": ["DATE","INTEGER","INTEGER","BIGINT","VARCHAR","INTEGER","VARCHAR","VARCHAR","INTEGER","INTEGER","DOUBLE","DOUBLE","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","INTEGER","BOOLEAN","BOOLEAN","BOOLEAN","BOOLEAN","DOUBLE"],
    "long_rng_store_dmd_frcst": ["INTEGER","VARCHAR","INTEGER","INTEGER","BIGINT","INTEGER","DOUBLE"],
}

PRIMARY_KEYS = {
    "calendar_dim": ["cal_dt", "geo_region_cd"],
    "store_dim": ["store_nbr"],
    "omni_item_dimensions": ["op_cmpny_cd", "wm_item_nbr"],
    "store_sales": ["bus_dt","geo_region_cd","rpt_cd","store_nbr","svc_chnl_nm","wm_item_nbr"],
    "store_invt": ["bus_dt","op_cmpny_cd","store_nbr","wm_item_nbr"],
    "long_rng_store_dmd_frcst": ["fcst_wm_yr_wk_nbr","geo_region_cd","op_cmpny_cd","store_nbr","wm_item_nbr","wm_yr_wk_nbr"],
}

MAPPING = {
    "calendar_dim": "calendar_day",
    "store_dim": "location",
    "omni_item_dimensions": "product",
    "store_sales": "sales_daily",
    "store_invt": "inventory_daily",
    "long_rng_store_dmd_frcst": "demand_forecast_weekly",
}


def _files(inventory: SourceInventory, dataset: str) -> list[str]:
    return [str(f.absolute_path) for f in inventory.files if f.path.startswith(dataset + "/")]


def _scan_sql(inventory: SourceInventory, dataset: str) -> str:
    files = _files(inventory, dataset)
    quoted = ",".join("'" + f.replace("'", "''") + "'" for f in files)
    return f"read_parquet([{quoted}], hive_partitioning=false, union_by_name=false)"


def _stamp_required_parquet(source: Path, target: Path) -> None:
    parquet = pq.ParquetFile(source)
    required = pa.schema(
        [pa.field(field.name, field.type, nullable=False, metadata=field.metadata) for field in parquet.schema_arrow],
        metadata=parquet.schema_arrow.metadata,
    )
    with pq.ParquetWriter(target, required, compression="zstd") as writer:
        for batch in parquet.iter_batches(batch_size=122_880):
            if any(column.null_count for column in batch.columns):
                raise ValueError("canonical required column contains nulls")
            writer.write_batch(pa.RecordBatch.from_arrays(batch.columns, schema=required))


def validate_source_data(con: duckdb.DuckDBPyConnection, inventory: SourceInventory) -> list[ValidationResult]:
    out: list[ValidationResult] = []
    declared = {d["dataset_name"]: d for d in inventory.manifest["datasets"]}
    for name, expected_columns in SOURCE_COLUMNS.items():
        scan = _scan_sql(inventory, name)
        try:
            desc = con.execute(f"DESCRIBE SELECT * FROM {scan}").fetchall()
        except duckdb.Error:
            out.append(ValidationResult("SRC_PARQUET_READ", "FAIL", name, 1, "Parquet dataset cannot be read"))
            continue
        schema = [(row[0], row[1]) for row in desc]
        expected_schema = list(zip(expected_columns, SOURCE_TYPES[name], strict=True))
        legacy_schema = list(zip(expected_columns, LEGACY_SOURCE_TYPES[name], strict=True))
        schema_ok = schema in (expected_schema, legacy_schema)
        out.append(ValidationResult("SRC_SCHEMA_EXACT", "PASS" if schema_ok else "FAIL", name, 0 if schema_ok else 1, "exact supported physical column and type contract"))
        count = con.execute(f"SELECT count(*) FROM {scan}").fetchone()[0]
        out.append(ValidationResult("SRC_ROW_COUNT", "PASS" if count == declared[name]["row_count"] else "FAIL", name, 0 if count == declared[name]["row_count"] else 1, "physical row count reconciles"))
        pk = ",".join(PRIMARY_KEYS[name])
        dupes = con.execute(f"SELECT count(*)-count(DISTINCT ({pk})) FROM {scan}").fetchone()[0]
        out.append(ValidationResult("SRC_PRIMARY_KEY", "PASS" if dupes == 0 else "FAIL", name, int(dupes), "primary key unique"))
        nulls = con.execute("SELECT count(*) FROM (SELECT * FROM " + scan + ") t WHERE " + " OR ".join(f'"{c}" IS NULL' for c in expected_columns)).fetchone()[0]
        out.append(ValidationResult("SRC_REQUIRED_NULL", "PASS" if nulls == 0 else "FAIL", name, int(nulls), "required values non-null"))
    checks = [
        ("SRC_CALENDAR_RULES", f"SELECT count(*) FROM {_scan_sql(inventory,'calendar_dim')} WHERE geo_region_cd <> 'US' OR cal_wk_day_nbr NOT BETWEEN 1 AND 7 OR cal_mth_nbr NOT BETWEEN 1 AND 12 OR cal_qtr_nbr NOT BETWEEN 1 AND 4 OR wm_week_nbr NOT BETWEEN 1 AND 53 OR wm_yr_wk_nbr <> wm_yr_nbr::INTEGER*100+wm_week_nbr::INTEGER OR fiscal_mth_nbr <> wm_mth_nbr OR fiscal_qtr_nbr <> wm_qtr_nbr OR fiscal_full_yr_nbr <> wm_yr_nbr OR ly_cal_dt <> ly_comp_visit_dt", "calendar_dim"),
        ("SRC_LOCATION_RULES", f"SELECT count(*) FROM {_scan_sql(inventory,'store_dim')} WHERE geo_region_cd <> 'US' OR op_cmpny_cd <> 0 OR NOT isfinite(lat_dgr) OR NOT isfinite(long_dgr) OR lat_dgr NOT BETWEEN -90 AND 90 OR long_dgr NOT BETWEEN -180 AND 180", "store_dim"),
        ("SRC_PRODUCT_RULES", f"SELECT count(*) FROM {_scan_sql(inventory,'omni_item_dimensions')} WHERE op_cmpny_cd < 0 OR wm_item_nbr < 0 OR NOT isfinite(base_unit_rtl_amt) OR base_unit_rtl_amt < 0 OR abs(base_unit_rtl_amt-round(base_unit_rtl_amt,2)) > 0.000001", "omni_item_dimensions"),
        ("SRC_SALES_DOMAIN", f"SELECT count(*) FROM {_scan_sql(inventory,'store_sales')} WHERE op_cmpny_cd <> 0 OR geo_region_cd <> 'US' OR rpt_cd NOT IN (0,7,8) OR svc_chnl_nm <> 'BIS' OR NOT isfinite(ty_sales_amt) OR NOT isfinite(ly_sales_amt) OR abs(ty_sales_amt-round(ty_sales_amt,2)) > 0.000001 OR abs(ly_sales_amt-round(ly_sales_amt,2)) > 0.000001", "store_sales"),
        ("SRC_INVENTORY_DOMAIN", f"SELECT count(*) FROM {_scan_sql(inventory,'store_invt')} WHERE op_cmpny_cd <> 0 OR geo_region_cd <> 'US' OR crncy_cd <> 'USD' OR NOT isfinite(ty_on_hand_rtl_amt) OR NOT isfinite(ly_on_hand_rtl_amt) OR NOT isfinite(curr_store_unit_rtl_amt) OR ty_on_hand_rtl_amt < 0 OR ly_on_hand_rtl_amt < 0 OR curr_store_unit_rtl_amt < 0 OR abs(ty_on_hand_rtl_amt-round(ty_on_hand_rtl_amt,2)) > 0.000001 OR abs(ly_on_hand_rtl_amt-round(ly_on_hand_rtl_amt,2)) > 0.000001 OR abs(curr_store_unit_rtl_amt-round(curr_store_unit_rtl_amt,2)) > 0.000001", "store_invt"),
        ("SRC_FORECAST_DOMAIN", f"SELECT count(*) FROM {_scan_sql(inventory,'long_rng_store_dmd_frcst')} WHERE op_cmpny_cd <> 0 OR geo_region_cd <> 'US' OR NOT isfinite(final_fcst_each_qty) OR final_fcst_each_qty < 0 OR fcst_wm_yr_wk_nbr >= wm_yr_wk_nbr OR fcst_wm_yr_wk_nbr%100 NOT BETWEEN 1 AND 53", "long_rng_store_dmd_frcst"),
    ]
    for rule, sql, dataset in checks:
        count = con.execute(sql).fetchone()[0]
        out.append(ValidationResult(rule, "PASS" if count == 0 else "FAIL", dataset, int(count), "source semantic contract"))
    # Cross-dataset references are independently checked, not trusted from producer claims.
    cal, loc, prod = (_scan_sql(inventory, n) for n in ("calendar_dim", "store_dim", "omni_item_dimensions"))
    for name, date_col, week_col in (("store_sales","bus_dt","wm_yr_wk_nbr"),("store_invt","bus_dt","wm_yr_wk_nbr")):
        fact = _scan_sql(inventory, name)
        sql = f"SELECT count(*) FROM {fact} f LEFT JOIN {cal} c ON f.{date_col}=c.cal_dt AND f.{week_col}=c.wm_yr_wk_nbr LEFT JOIN {loc} l ON f.store_nbr=l.store_nbr AND f.op_cmpny_cd=l.op_cmpny_cd LEFT JOIN {prod} p ON f.wm_item_nbr=p.wm_item_nbr AND f.op_cmpny_cd=p.op_cmpny_cd WHERE c.cal_dt IS NULL OR l.store_nbr IS NULL OR p.wm_item_nbr IS NULL"
        count = con.execute(sql).fetchone()[0]
        out.append(ValidationResult("SRC_REFERENCES", "PASS" if count == 0 else "FAIL", name, int(count), "dimension references resolve"))
    fact = _scan_sql(inventory, "long_rng_store_dmd_frcst")
    sql = f"SELECT count(*) FROM {fact} f LEFT JOIN (SELECT DISTINCT wm_yr_wk_nbr FROM {cal}) tc ON f.wm_yr_wk_nbr=tc.wm_yr_wk_nbr LEFT JOIN {loc} l ON f.store_nbr=l.store_nbr AND f.op_cmpny_cd=l.op_cmpny_cd LEFT JOIN {prod} p ON f.wm_item_nbr=p.wm_item_nbr AND f.op_cmpny_cd=p.op_cmpny_cd WHERE tc.wm_yr_wk_nbr IS NULL OR l.store_nbr IS NULL OR p.wm_item_nbr IS NULL"
    count = con.execute(sql).fetchone()[0]
    out.append(ValidationResult("SRC_REFERENCES", "PASS" if count == 0 else "FAIL", "long_rng_store_dmd_frcst", int(count), "dimension references resolve"))
    return out


def canonicalize(con: duckdb.DuckDBPyConnection, inventory: SourceInventory, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    s = lambda n: _scan_sql(inventory, n)
    locid = "'loc_'||sha256('memento|v1|location|walmart|'||op_cmpny_cd::VARCHAR||'|'||store_nbr::VARCHAR)"
    prodid = "'prd_'||sha256('memento|v1|product|walmart|'||op_cmpny_cd::VARCHAR||'|'||wm_item_nbr::VARCHAR)"
    retail_type = "CASE rpt_cd " + " ".join(f"WHEN {code} THEN '{name}'" for code, name in RETAIL_TYPE_MAP.items()) + " END"
    queries = {
        "calendar_day": f"SELECT 'walmart-us-454'::VARCHAR retail_calendar_id,cal_dt::DATE calendar_date,cal_day_nbr::UTINYINT calendar_day_of_month,cal_wk_day_nbr::UTINYINT calendar_weekday_number,cal_wk_day_nm::VARCHAR calendar_weekday_name,cal_mth_nbr::UTINYINT calendar_month_number,cal_mth_nm::VARCHAR calendar_month_name,cal_qtr_nbr::UTINYINT calendar_quarter_number,cal_full_yr_nbr::SMALLINT calendar_year,wm_day_nbr::USMALLINT retail_day_number,wm_week_nbr::UTINYINT retail_week_number,wm_mth_nbr::UTINYINT retail_month_number,wm_qtr_nbr::UTINYINT retail_quarter_number,wm_yr_nbr::SMALLINT retail_year,wm_yr_wk_nbr::INTEGER retail_year_week,ly_comp_visit_dt::DATE comparable_calendar_date,ly_comp_yr_wk_nbr::INTEGER comparable_retail_year_week FROM {s('calendar_dim')} ORDER BY cal_dt",
        "location": f"SELECT {locid}::VARCHAR location_id,'walmart'::VARCHAR source_system,op_cmpny_cd::VARCHAR source_company_id,store_nbr::VARCHAR source_location_id,'US'::VARCHAR country_code,store_nm::VARCHAR location_name,store_type_cd::VARCHAR source_location_type_code,store_type_desc::VARCHAR source_location_type_name,open_status_cd::VARCHAR source_status_code,open_status_desc::VARCHAR source_status_name,city_nm::VARCHAR city_name,cnty_nm::VARCHAR county_name,state_prov_cd::VARCHAR state_province_code,st_prov_nm::VARCHAR state_province_name,postal_cd::VARCHAR postal_code,lat_dgr::DOUBLE latitude,long_dgr::DOUBLE longitude,region_nbr::VARCHAR source_region_id,region_nm::VARCHAR source_region_name,market_nbr::VARCHAR source_market_id,market_nm::VARCHAR source_market_name,tz_cd::VARCHAR source_timezone_code,tz_nm::VARCHAR timezone_name FROM {s('store_dim')} ORDER BY op_cmpny_cd,store_nbr",
        "product": f"SELECT {prodid}::VARCHAR product_id,'walmart'::VARCHAR source_system,op_cmpny_cd::VARCHAR source_company_id,wm_item_nbr::VARCHAR source_product_id,item_nm::VARCHAR product_name,item_desc::VARCHAR product_description,upc_nbr::VARCHAR upc,brand_nm::VARCHAR brand_name,omni_dept_nbr::VARCHAR source_department_id,omni_dept_desc::VARCHAR source_department_name,omni_catg_nbr::VARCHAR source_category_id,omni_catg_desc::VARCHAR source_category_name,omni_subcatg_nbr::VARCHAR source_subcategory_id,omni_subcatg_desc::VARCHAR source_subcategory_name,fineline_nbr::VARCHAR source_fineline_id,fineline_desc::VARCHAR source_fineline_name,season_cd::VARCHAR source_season_code,item_status_cd::VARCHAR source_status_code,item_effective_dt::DATE effective_date,item_repl_ind::BOOLEAN replenishment_enabled,retail_uom_cd::VARCHAR unit_of_measure_code,round(base_unit_rtl_amt,2)::DECIMAL(20,2) base_unit_retail_amount,'USD'::VARCHAR currency_code,item_type_cd::VARCHAR source_item_type_code,repl_type_cd::VARCHAR source_replenishment_type_code FROM {s('omni_item_dimensions')} ORDER BY op_cmpny_cd,wm_item_nbr",
        "sales_daily": f"SELECT bus_dt::DATE business_date,'walmart-us-454'::VARCHAR retail_calendar_id,wm_yr_wk_nbr::INTEGER retail_year_week,{locid}::VARCHAR location_id,{prodid}::VARCHAR product_id,({retail_type})::VARCHAR retail_type_code,svc_chnl_nm::VARCHAR sales_channel_code,ty_qty::BIGINT sales_quantity,round(ty_sales_amt,2)::DECIMAL(20,2) sales_amount,ly_qty::BIGINT source_comparison_quantity,round(ly_sales_amt,2)::DECIMAL(20,2) source_comparison_amount,'USD'::VARCHAR currency_code FROM {s('store_sales')} ORDER BY bus_dt,op_cmpny_cd,store_nbr,wm_item_nbr,rpt_cd,svc_chnl_nm",
        "inventory_daily": f"SELECT bus_dt::DATE business_date,'walmart-us-454'::VARCHAR retail_calendar_id,wm_yr_wk_nbr::INTEGER retail_year_week,{locid}::VARCHAR location_id,{prodid}::VARCHAR product_id,crncy_cd::VARCHAR currency_code,mds_fam_id::VARCHAR source_merchandise_family_id,ty_on_hand_qty::BIGINT on_hand_quantity,ly_on_hand_qty::BIGINT source_comparison_on_hand_quantity,round(ty_on_hand_rtl_amt,2)::DECIMAL(20,2) on_hand_retail_amount,round(ly_on_hand_rtl_amt,2)::DECIMAL(20,2) source_comparison_on_hand_retail_amount,ty_on_order_qty::BIGINT on_order_quantity,ly_on_order_qty::BIGINT source_comparison_on_order_quantity,ty_in_transit_qty::BIGINT in_transit_quantity,ly_in_transit_qty::BIGINT source_comparison_in_transit_quantity,ty_rcpt_qty::BIGINT receipt_quantity,ly_rcpt_qty::BIGINT source_comparison_receipt_quantity,ty_max_shelf_qty::BIGINT maximum_shelf_quantity,ly_max_shelf_qty::BIGINT source_comparison_maximum_shelf_quantity,ty_traited_ind::BOOLEAN assorted,ly_traited_ind::BOOLEAN source_comparison_assorted,ty_repl_ind::BOOLEAN replenishment_enabled,ly_repl_ind::BOOLEAN source_comparison_replenishment_enabled,round(curr_store_unit_rtl_amt,2)::DECIMAL(20,2) current_unit_retail_amount FROM {s('store_invt')} ORDER BY bus_dt,op_cmpny_cd,store_nbr,wm_item_nbr",
        "demand_forecast_weekly": f"SELECT 'walmart-us-454'::VARCHAR retail_calendar_id,fcst_wm_yr_wk_nbr::INTEGER forecast_created_retail_year_week,wm_yr_wk_nbr::INTEGER target_retail_year_week,{locid}::VARCHAR location_id,{prodid}::VARCHAR product_id,final_fcst_each_qty::DECIMAL(20,6) forecast_quantity FROM {s('long_rng_store_dmd_frcst')} ORDER BY fcst_wm_yr_wk_nbr,wm_yr_wk_nbr,op_cmpny_cd,store_nbr,wm_item_nbr",
    }
    for table, query in queries.items():
        table_root = root / table
        table_root.mkdir()
        optional_path = table_root / "part-00000.optional.parquet"
        target_path = table_root / "part-00000.parquet"
        escaped = str(optional_path).replace("'", "''")
        con.execute(f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)")
        _stamp_required_parquet(optional_path, target_path)
        optional_path.unlink()
