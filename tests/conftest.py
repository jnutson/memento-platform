from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_release(root: Path) -> Path:
    release = root / "release" / "observable"
    release.mkdir(parents=True)
    con = duckdb.connect()
    queries = {
        "calendar_dim": """SELECT * FROM (VALUES
          (DATE '2026-01-31','US',31,7,'Saturday',1,'January',1,2026,1,1,1,1,2026,1,1,2026,202601,DATE '2025-02-01',DATE '2025-02-01',202501),
          (DATE '2026-02-07','US',7,7,'Saturday',2,'February',1,2026,8,2,1,1,2026,1,1,2026,202602,DATE '2025-02-08',DATE '2025-02-08',202502)
        ) t(cal_dt,geo_region_cd,cal_day_nbr,cal_wk_day_nbr,cal_wk_day_nm,cal_mth_nbr,cal_mth_nm,cal_qtr_nbr,cal_full_yr_nbr,wm_day_nbr,wm_week_nbr,wm_mth_nbr,wm_qtr_nbr,wm_yr_nbr,fiscal_mth_nbr,fiscal_qtr_nbr,fiscal_full_yr_nbr,wm_yr_wk_nbr,ly_cal_dt,ly_comp_visit_dt,ly_comp_yr_wk_nbr)""",
        "store_dim": """SELECT 10::INTEGER store_nbr,'US'::VARCHAR geo_region_cd,0::INTEGER op_cmpny_cd,'Synthetic Store'::VARCHAR store_nm,'SC'::VARCHAR store_type_cd,'Supercenter'::VARCHAR store_type_desc,'O'::VARCHAR open_status_cd,'Open'::VARCHAR open_status_desc,'Testville'::VARCHAR city_nm,'Test'::VARCHAR cnty_nm,'CA'::VARCHAR state_prov_cd,'California'::VARCHAR st_prov_nm,'00000'::VARCHAR postal_cd,34.0::DOUBLE lat_dgr,-118.0::DOUBLE long_dgr,1::INTEGER region_nbr,'West'::VARCHAR region_nm,2::INTEGER market_nbr,'Demo'::VARCHAR market_nm,'PST'::VARCHAR tz_cd,'America/Los_Angeles'::VARCHAR tz_nm""",
        "omni_item_dimensions": """SELECT 0::INTEGER op_cmpny_cd,100::BIGINT wm_item_nbr,'Synthetic Item'::VARCHAR item_nm,'Synthetic fixture item'::VARCHAR item_desc,'000000000100'::VARCHAR upc_nbr,'Demo'::VARCHAR brand_nm,1::INTEGER omni_dept_nbr,'Dept'::VARCHAR omni_dept_desc,2::INTEGER omni_catg_nbr,'Category'::VARCHAR omni_catg_desc,3::INTEGER omni_subcatg_nbr,'Subcategory'::VARCHAR omni_subcatg_desc,4::INTEGER fineline_nbr,'Fineline'::VARCHAR fineline_desc,'ALL'::VARCHAR season_cd,'A'::VARCHAR item_status_cd,DATE '2025-01-01' item_effective_dt,true::BOOLEAN item_repl_ind,'EA'::VARCHAR retail_uom_cd,2.50::DOUBLE base_unit_rtl_amt,'ST'::VARCHAR item_type_cd,'R'::VARCHAR repl_type_cd""",
        "store_sales": """SELECT DATE '2026-01-31' bus_dt,'US'::VARCHAR geo_region_cd,0::INTEGER rpt_cd,10::INTEGER store_nbr,'BIS'::VARCHAR svc_chnl_nm,100::BIGINT wm_item_nbr,0::INTEGER op_cmpny_cd,202601::INTEGER wm_yr_wk_nbr,2::INTEGER ty_qty,5.00::DOUBLE ty_sales_amt,1::INTEGER ly_qty,2.50::DOUBLE ly_sales_amt""",
        "store_invt": """SELECT DATE '2026-01-31' bus_dt,0::INTEGER op_cmpny_cd,10::INTEGER store_nbr,100::BIGINT wm_item_nbr,'US'::VARCHAR geo_region_cd,202601::INTEGER wm_yr_wk_nbr,'USD'::VARCHAR crncy_cd,'1'::VARCHAR mds_fam_id,5::INTEGER ty_on_hand_qty,4::INTEGER ly_on_hand_qty,12.50::DOUBLE ty_on_hand_rtl_amt,10.00::DOUBLE ly_on_hand_rtl_amt,1::INTEGER ty_on_order_qty,0::INTEGER ly_on_order_qty,0::INTEGER ty_in_transit_qty,0::INTEGER ly_in_transit_qty,2::INTEGER ty_rcpt_qty,1::INTEGER ly_rcpt_qty,10::INTEGER ty_max_shelf_qty,10::INTEGER ly_max_shelf_qty,true::BOOLEAN ty_traited_ind,true::BOOLEAN ly_traited_ind,true::BOOLEAN ty_repl_ind,true::BOOLEAN ly_repl_ind,2.50::DOUBLE curr_store_unit_rtl_amt""",
        "long_rng_store_dmd_frcst": """SELECT 202601::INTEGER fcst_wm_yr_wk_nbr,'US'::VARCHAR geo_region_cd,0::INTEGER op_cmpny_cd,10::INTEGER store_nbr,100::BIGINT wm_item_nbr,202602::INTEGER wm_yr_wk_nbr,3.25::DOUBLE final_fcst_each_qty""",
    }
    primary_keys = {
        "calendar_dim":["cal_dt","geo_region_cd"],"store_dim":["store_nbr"],"omni_item_dimensions":["op_cmpny_cd","wm_item_nbr"],
        "store_sales":["bus_dt","geo_region_cd","rpt_cd","store_nbr","svc_chnl_nm","wm_item_nbr"],
        "store_invt":["bus_dt","op_cmpny_cd","store_nbr","wm_item_nbr"],
        "long_rng_store_dmd_frcst":["fcst_wm_yr_wk_nbr","geo_region_cd","op_cmpny_cd","store_nbr","wm_item_nbr","wm_yr_wk_nbr"],
    }
    files, datasets = [], []
    partitioned = {"store_sales", "store_invt", "long_rng_store_dmd_frcst"}
    for name, query in queries.items():
        folder = release / name / "wm_yr_wk_nbr=202601" if name in partitioned else release / name
        folder.mkdir(parents=True)
        path = folder / ("part-shard-0000.parquet" if name in partitioned else "part-00000.parquet")
        con.execute(f"COPY ({query}) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        rows = con.execute(f"SELECT count(*) FROM ({query})").fetchone()[0]
        rel = str(path.relative_to(release))
        files.append({"path":rel,"bytes":path.stat().st_size,"sha256":digest(path)})
        tree = hashlib.sha256()
        tree.update(path.relative_to(release / name).as_posix().encode())
        tree.update(bytes.fromhex(digest(path)))
        partitions = ["wm_yr_wk_nbr", "store_shard"] if name in partitioned else []
        datasets.append({"classification":"observable","compression":"zstd","dataset_name":name,"duplicate_check":"passed","file_count":1,"maximum_date":None,"minimum_date":None,"null_check":"passed","parquet_writer_version":"fixture","partition_columns":partitions,"primary_key":primary_keys[name],"referential_integrity":"passed","relative_output_path":name,"row_count":rows,"schema_checksum":"0"*64,"schema_version":"1.0.0","sha256":tree.hexdigest()})
    manifest = {"as_of":"2027-01-30T00:00:00Z","dataset_type":"observable","datasets":datasets,"files":files,"manifest_schema_version":"1.0.0","release_gates":{"GT-01":True},"release_id":"437b6da3ad31abe0-20270130T000000Z"}
    path = release / "manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True))
    return path


@pytest.fixture
def release_manifest(tmp_path: Path) -> Path:
    return write_release(tmp_path)
