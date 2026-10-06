from __future__ import annotations

from pathlib import Path

import duckdb

from .models import SourceInventory, ValidationResult
from .walmart import _scan_sql


SOURCE_COLUMNS = {
    "dim_item": ["company_id", "company_item_id", "company_item_name", "display_brand_id", "op_cmpny_cd", "wm_item_nbr", "effective_from", "effective_to"],
    "retailer_replenishment_commitment": ["retailer_order_id", "order_line_nbr", "event_version", "store_nbr", "op_cmpny_cd", "wm_item_nbr", "ordered_qty", "invoiced_qty", "received_qty", "order_created_at", "approved_to_ship_at", "dc_invoiced_at", "expected_store_receipt_date", "actual_store_receipt_at", "status_cd", "known_at"],
    "item_reaction_constraint": ["company_id", "item_scope_type_cd", "item_scope_id", "minimum_reaction_days", "effective_from", "effective_to"],
    "company_item_economics": ["company_id", "company_item_id", "currency_code", "unit_cost_amount", "effective_from", "effective_to"],
}
SOURCE_TYPES = {
    "dim_item": ["VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR", "TINYINT", "BIGINT", "DATE", "DATE"],
    "retailer_replenishment_commitment": ["VARCHAR", "INTEGER", "INTEGER", "INTEGER", "TINYINT", "BIGINT", "INTEGER", "INTEGER", "INTEGER", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITH TIME ZONE", "DATE", "TIMESTAMP WITH TIME ZONE", "VARCHAR", "TIMESTAMP WITH TIME ZONE"],
    "item_reaction_constraint": ["VARCHAR", "VARCHAR", "VARCHAR", "INTEGER", "DATE", "DATE"],
    "company_item_economics": ["VARCHAR", "VARCHAR", "VARCHAR", "DECIMAL(20,2)", "DATE", "DATE"],
}
PRIMARY_KEYS = {
    "dim_item": ["company_id", "company_item_id"],
    "retailer_replenishment_commitment": ["retailer_order_id", "order_line_nbr", "event_version"],
    "item_reaction_constraint": ["company_id", "item_scope_type_cd", "item_scope_id", "effective_from"],
    "company_item_economics": ["company_id", "company_item_id", "effective_from"],
}
MAPPING = {
    "dim_item": "company_item",
    "retailer_replenishment_commitment": "replenishment_commitment",
    "item_reaction_constraint": "reaction_constraint",
    "company_item_economics": "company_item_economics",
}
ALLOWED_STATUSES = {"ordered", "approved_to_ship", "in_transit", "partially_received", "received", "cancelled"}


def validate_extension_data(
    con: duckdb.DuckDBPyConnection,
    extension: SourceInventory,
    walmart: SourceInventory,
) -> list[ValidationResult]:
    out: list[ValidationResult] = []
    declared = {d["dataset_name"]: d for d in extension.manifest["datasets"]}
    for name, columns in SOURCE_COLUMNS.items():
        scan = _scan_sql(extension, name)
        try:
            desc = [(row[0], row[1]) for row in con.execute(f"DESCRIBE SELECT * FROM {scan}").fetchall()]
        except duckdb.Error:
            out.append(ValidationResult("EXT_PARQUET_READ", "FAIL", name, 1, "extension Parquet cannot be read"))
            continue
        expected = list(zip(columns, SOURCE_TYPES[name], strict=True))
        out.append(ValidationResult("EXT_SCHEMA_EXACT", "PASS" if desc == expected else "FAIL", name, 0 if desc == expected else 1, "exact extension schema"))
        count = con.execute(f"SELECT count(*) FROM {scan}").fetchone()[0]
        out.append(ValidationResult("EXT_ROW_COUNT", "PASS" if count == declared[name]["row_count"] else "FAIL", name, 0 if count == declared[name]["row_count"] else 1, "row count reconciles"))
        key = ",".join(PRIMARY_KEYS[name])
        dupes = con.execute(f"SELECT count(*)-count(DISTINCT ({key})) FROM {scan}").fetchone()[0]
        out.append(ValidationResult("EXT_PRIMARY_KEY", "PASS" if dupes == 0 else "FAIL", name, int(dupes), "extension primary key unique"))
        required = [c for c in columns if c not in {"effective_to", "approved_to_ship_at", "dc_invoiced_at", "expected_store_receipt_date", "actual_store_receipt_at"}]
        nulls = con.execute(f"SELECT count(*) FROM {scan} WHERE " + " OR ".join(f'"{c}" IS NULL' for c in required)).fetchone()[0]
        out.append(ValidationResult("EXT_REQUIRED_NULL", "PASS" if nulls == 0 else "FAIL", name, int(nulls), "required extension values non-null"))

    dim, po, reaction, economics = (_scan_sql(extension, n) for n in SOURCE_COLUMNS)
    products, stores = _scan_sql(walmart, "omni_item_dimensions"), _scan_sql(walmart, "store_dim")
    as_of = str(extension.manifest.get("as_of") or extension.manifest.get("release_as_of") or walmart.manifest.get("as_of"))
    observation_date = con.execute(f"SELECT max(bus_dt) FROM {_scan_sql(walmart, 'store_invt')}").fetchone()[0]
    checks = [
        ("EXT_ITEM_DOMAIN", f"SELECT count(*) FROM {dim} WHERE company_id<>'MIRO_TOYS' OR display_brand_id<>'MIRO_SPARK' OR effective_to<effective_from", "dim_item"),
        ("EXT_ITEM_REFERENCE", f"SELECT count(*) FROM {dim} d LEFT JOIN {products} p USING(op_cmpny_cd,wm_item_nbr) WHERE p.wm_item_nbr IS NULL OR p.brand_nm<>'BRAND_A'", "dim_item"),
        ("EXT_PO_DOMAIN", f"SELECT count(*) FROM {po} WHERE event_version<1 OR ordered_qty<0 OR invoiced_qty<0 OR received_qty<0 OR invoiced_qty>ordered_qty OR received_qty>invoiced_qty OR status_cd NOT IN ({','.join(repr(x) for x in sorted(ALLOWED_STATUSES))}) OR known_at>TIMESTAMPTZ '{as_of}' OR actual_store_receipt_at<order_created_at", "retailer_replenishment_commitment"),
        ("EXT_PO_REFERENCE", f"SELECT count(*) FROM {po} r LEFT JOIN {products} p USING(op_cmpny_cd,wm_item_nbr) LEFT JOIN {stores} s USING(op_cmpny_cd,store_nbr) WHERE p.wm_item_nbr IS NULL OR s.store_nbr IS NULL", "retailer_replenishment_commitment"),
        ("EXT_PO_VERSION_ORDER", f"SELECT count(*) FROM (SELECT *,lag(known_at) OVER(PARTITION BY retailer_order_id,order_line_nbr ORDER BY event_version) prior_known,lag(event_version) OVER(PARTITION BY retailer_order_id,order_line_nbr ORDER BY event_version) prior_version FROM {po}) WHERE prior_version IS NOT NULL AND (event_version<>prior_version+1 OR known_at<prior_known)", "retailer_replenishment_commitment"),
        ("EXT_REACTION_DOMAIN", f"SELECT count(*) FROM {reaction} WHERE company_id<>'MIRO_TOYS' OR item_scope_type_cd NOT IN ('all','brand','item') OR minimum_reaction_days<0 OR effective_to<effective_from", "item_reaction_constraint"),
        ("EXT_REACTION_RESOLUTION", f"""SELECT count(*) FROM {dim} d WHERE
          (SELECT count(*) FROM {reaction} r WHERE r.company_id=d.company_id AND r.effective_from<=DATE '{observation_date}' AND (r.effective_to IS NULL OR r.effective_to>=DATE '{observation_date}') AND r.item_scope_type_cd='item' AND r.item_scope_id=d.company_item_id)>1 OR
          ((SELECT count(*) FROM {reaction} r WHERE r.company_id=d.company_id AND r.effective_from<=DATE '{observation_date}' AND (r.effective_to IS NULL OR r.effective_to>=DATE '{observation_date}') AND r.item_scope_type_cd='item' AND r.item_scope_id=d.company_item_id)=0 AND
           ((SELECT count(*) FROM {reaction} r WHERE r.company_id=d.company_id AND r.effective_from<=DATE '{observation_date}' AND (r.effective_to IS NULL OR r.effective_to>=DATE '{observation_date}') AND r.item_scope_type_cd='brand' AND r.item_scope_id=d.display_brand_id)>1 OR
            ((SELECT count(*) FROM {reaction} r WHERE r.company_id=d.company_id AND r.effective_from<=DATE '{observation_date}' AND (r.effective_to IS NULL OR r.effective_to>=DATE '{observation_date}') AND r.item_scope_type_cd='brand' AND r.item_scope_id=d.display_brand_id)=0 AND
             (SELECT count(*) FROM {reaction} r WHERE r.company_id=d.company_id AND r.effective_from<=DATE '{observation_date}' AND (r.effective_to IS NULL OR r.effective_to>=DATE '{observation_date}') AND r.item_scope_type_cd='all')<>1)))""", "item_reaction_constraint"),
        ("EXT_ECONOMICS_DOMAIN", f"SELECT count(*) FROM {economics} WHERE company_id<>'MIRO_TOYS' OR currency_code<>'USD' OR unit_cost_amount<0 OR effective_to<effective_from", "company_item_economics"),
        ("EXT_ECONOMICS_REFERENCE", f"SELECT count(*) FROM {economics} e LEFT JOIN {dim} d USING(company_id,company_item_id) WHERE d.company_item_id IS NULL", "company_item_economics"),
        ("EXT_ECONOMICS_OVERLAP", f"""SELECT count(*) FROM {economics} a JOIN {economics} b
          ON a.company_id=b.company_id AND a.company_item_id=b.company_item_id
         AND (a.effective_from<b.effective_from OR (a.effective_from=b.effective_from AND coalesce(a.effective_to,DATE '9999-12-31')<coalesce(b.effective_to,DATE '9999-12-31')))
         AND a.effective_from<=coalesce(b.effective_to,DATE '9999-12-31')
         AND b.effective_from<=coalesce(a.effective_to,DATE '9999-12-31')""", "company_item_economics"),
        ("EXT_ECONOMICS_RESOLUTION", f"""SELECT count(*) FROM {dim} d WHERE
          (SELECT count(*) FROM {economics} e WHERE e.company_id=d.company_id AND e.company_item_id=d.company_item_id
           AND e.effective_from<=DATE '{observation_date}' AND (e.effective_to IS NULL OR e.effective_to>=DATE '{observation_date}'))<>1""", "company_item_economics"),
    ]
    for rule, sql, dataset in checks:
        count = con.execute(sql).fetchone()[0]
        out.append(ValidationResult(rule, "PASS" if count == 0 else "FAIL", dataset, int(count), "extension semantic contract"))
    inventory = _scan_sql(walmart, "store_invt")
    reconciliation = con.execute(f"""WITH versions AS (
          SELECT *,lag(received_qty,1,0) OVER(PARTITION BY retailer_order_id,order_line_nbr ORDER BY event_version) prior_received
          FROM {po} WHERE known_at<=TIMESTAMPTZ '{as_of}'
        ), latest AS (
          SELECT * FROM versions QUALIFY row_number() OVER(PARTITION BY retailer_order_id,order_line_nbr ORDER BY event_version DESC)=1
        ), derived AS (
          SELECT store_nbr,op_cmpny_cd,wm_item_nbr,
            sum(CASE WHEN status_cd='cancelled' THEN 0 ELSE greatest(ordered_qty-invoiced_qty,0) END) open_units,
            sum(CASE WHEN status_cd='cancelled' THEN 0 ELSE greatest(invoiced_qty-received_qty,0) END) transit_units
          FROM latest GROUP BY ALL
        ), receipts AS (
          SELECT store_nbr,op_cmpny_cd,wm_item_nbr,sum(greatest(received_qty-prior_received,0)) receipt_units
          FROM versions WHERE cast(known_at AS DATE)=DATE '{observation_date}' GROUP BY ALL
        ), compared AS (
          SELECT i.store_nbr,i.op_cmpny_cd,i.wm_item_nbr,
            abs(coalesce(d.open_units,0)-i.ty_on_order_qty)::DOUBLE/greatest(coalesce(d.open_units,0),i.ty_on_order_qty,1) open_rate,
            abs(coalesce(d.transit_units,0)-i.ty_in_transit_qty)::DOUBLE/greatest(coalesce(d.transit_units,0),i.ty_in_transit_qty,1) transit_rate,
            abs(coalesce(r.receipt_units,0)-i.ty_rcpt_qty)::DOUBLE/greatest(coalesce(r.receipt_units,0),i.ty_rcpt_qty,1) receipt_rate
          FROM {inventory} i JOIN {dim} m USING(op_cmpny_cd,wm_item_nbr)
          LEFT JOIN derived d USING(store_nbr,op_cmpny_cd,wm_item_nbr)
          LEFT JOIN receipts r USING(store_nbr,op_cmpny_cd,wm_item_nbr)
          WHERE i.bus_dt=DATE '{observation_date}'
        ) SELECT coalesce(max(greatest(open_rate,transit_rate,receipt_rate)),0) FROM compared""").fetchone()[0]
    out.append(ValidationResult("EXT_INBOUND_RECONCILIATION", "PASS" if reconciliation <= 0.10 else "FAIL", "retailer_replenishment_commitment", 0 if reconciliation <= 0.10 else 1, "observation-date inbound states reconcile within tolerance"))
    return out


def canonicalize_extension(con: duckdb.DuckDBPyConnection, source: SourceInventory, root: Path) -> None:
    s = lambda name: _scan_sql(source, name)
    location_id = "'loc_'||sha256('memento|v1|location|walmart|'||op_cmpny_cd::VARCHAR||'|'||store_nbr::VARCHAR)"
    product_id = "'prd_'||sha256('memento|v1|product|walmart|'||op_cmpny_cd::VARCHAR||'|'||wm_item_nbr::VARCHAR)"
    queries = {
        "company_item": f"SELECT company_id::VARCHAR company_id,company_item_id::VARCHAR company_item_id,company_item_name::VARCHAR company_item_name,display_brand_id::VARCHAR display_brand_id,{product_id}::VARCHAR product_id,op_cmpny_cd::VARCHAR source_company_id,wm_item_nbr::VARCHAR source_product_id,effective_from::DATE effective_from,effective_to::DATE effective_to FROM {s('dim_item')} ORDER BY company_id,company_item_id",
        "replenishment_commitment": f"SELECT retailer_order_id::VARCHAR retailer_order_id,order_line_nbr::INTEGER order_line_number,event_version::INTEGER event_version,{location_id}::VARCHAR location_id,{product_id}::VARCHAR product_id,ordered_qty::BIGINT ordered_quantity,invoiced_qty::BIGINT invoiced_quantity,received_qty::BIGINT received_quantity,order_created_at::TIMESTAMPTZ order_created_at,approved_to_ship_at::TIMESTAMPTZ approved_to_ship_at,dc_invoiced_at::TIMESTAMPTZ dc_invoiced_at,expected_store_receipt_date::DATE expected_store_receipt_date,actual_store_receipt_at::TIMESTAMPTZ actual_store_receipt_at,status_cd::VARCHAR status_code,known_at::TIMESTAMPTZ known_at FROM {s('retailer_replenishment_commitment')} ORDER BY retailer_order_id,order_line_nbr,event_version",
        "reaction_constraint": f"SELECT company_id::VARCHAR company_id,item_scope_type_cd::VARCHAR item_scope_type_code,item_scope_id::VARCHAR item_scope_id,minimum_reaction_days::INTEGER minimum_reaction_days,effective_from::DATE effective_from,effective_to::DATE effective_to FROM {s('item_reaction_constraint')} ORDER BY company_id,item_scope_type_cd,item_scope_id,effective_from",
        "company_item_economics": f"SELECT company_id::VARCHAR company_id,company_item_id::VARCHAR company_item_id,currency_code::VARCHAR currency_code,unit_cost_amount::DECIMAL(20,2) unit_cost_amount,effective_from::DATE effective_from,effective_to::DATE effective_to FROM {s('company_item_economics')} ORDER BY company_id,company_item_id,effective_from",
    }
    for table, query in queries.items():
        folder = root / table
        folder.mkdir()
        optional = folder / "part-00000.optional.parquet"
        target = folder / "part-00000.parquet"
        escaped = str(optional).replace("'", "''")
        con.execute("COPY (" + query + f") TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)")
        # Extension schemas intentionally contain nullable fields, so preserve Arrow
        # nullability instead of applying the all-required Walmart canonical stamp.
        optional.replace(target)
