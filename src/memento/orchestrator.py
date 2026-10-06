from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .canonical import CONTRACT_VERSION, SCHEMAS
from .manifest import canonical_json, inspect_manifest, sha256_file, validate_manifest_contract
from .models import IngestionFailure, ValidationResult
from .miro import MAPPING as MIRO_MAPPING, canonicalize_extension, validate_extension_data
from .release_set import inspect_release_set, release_set_identity, validate_release_set
from .walmart import ADAPTER_ID, ADAPTER_VERSION, MAPPING, TRANSFORMATION_VERSION, VALIDATION_VERSION, canonicalize, validate_source_data

LOG = logging.getLogger("memento.ingestion")


def _ensure_pass(phase: str, results: list[ValidationResult]) -> None:
    if any(r.severity == "FAIL" for r in results):
        raise IngestionFailure(phase, results)


def _safe_data_root(root: Path) -> Path:
    if root.exists() and root.is_symlink():
        raise ValueError("data root must be a non-symlink directory")
    resolved = root.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise ValueError("data root must be a non-symlink directory")
    return resolved


def _dataset_id(source_hash: str) -> str:
    identity = {"source_manifest_sha256": source_hash,"adapter": ADAPTER_VERSION,"canonical": CONTRACT_VERSION,"transformation": TRANSFORMATION_VERSION,"validation": VALIDATION_VERSION}
    return "mds_" + hashlib.sha256(canonical_json(identity)).hexdigest()


def _release_set_dataset_id(identity: bytes) -> str:
    versions = {"adapter": ADAPTER_VERSION, "canonical": CONTRACT_VERSION, "transformation": TRANSFORMATION_VERSION, "validation": VALIDATION_VERSION}
    return "mds_" + hashlib.sha256(identity + canonical_json(versions)).hexdigest()


def _canonical_validation(con: duckdb.DuckDBPyConnection, candidate: Path, expected: dict[str, int]) -> list[ValidationResult]:
    out: list[ValidationResult] = []
    keys = {
        "calendar_day":"retail_calendar_id,calendar_date", "location":"location_id", "product":"product_id",
        "sales_daily":"business_date,location_id,product_id,retail_type_code,sales_channel_code",
        "inventory_daily":"business_date,location_id,product_id",
        "demand_forecast_weekly":"forecast_created_retail_year_week,target_retail_year_week,location_id,product_id",
    }
    for table, pk in keys.items():
        path = str(candidate / table / "*.parquet").replace("'", "''")
        scan = f"read_parquet('{path}')"
        description = [(row[0], row[1]) for row in con.execute(f"DESCRIBE SELECT * FROM {scan}").fetchall()]
        out.append(ValidationResult("CAN_SCHEMA_EXACT", "PASS" if description == SCHEMAS[table] else "FAIL", table, 0 if description == SCHEMAS[table] else 1, "exact canonical names, order, and types"))
        required = " OR ".join(f'"{name}" IS NULL' for name, _ in SCHEMAS[table])
        null_count = con.execute(f"SELECT count(*) FROM {scan} WHERE {required}").fetchone()[0]
        out.append(ValidationResult("CAN_REQUIRED_NULL", "PASS" if null_count == 0 else "FAIL", table, int(null_count), "required canonical values non-null"))
        count, dupes = con.execute(f"SELECT count(*),count(*)-count(DISTINCT ({pk})) FROM {scan}").fetchone()
        want = expected[table]
        out.append(ValidationResult("CAN_ROW_COUNT", "PASS" if count == want else "FAIL", table, 0 if count == want else 1, "source and canonical row counts reconcile"))
        out.append(ValidationResult("CAN_PRIMARY_KEY", "PASS" if dupes == 0 else "FAIL", table, int(dupes), "canonical primary key unique"))
    base = lambda t: "read_parquet('" + str(candidate / t / "*.parquet").replace("'", "''") + "')"
    for table in ("sales_daily", "inventory_daily"):
        count = con.execute(f"SELECT count(*) FROM {base(table)} f LEFT JOIN {base('calendar_day')} c ON f.business_date=c.calendar_date AND f.retail_year_week=c.retail_year_week LEFT JOIN {base('location')} l USING(location_id) LEFT JOIN {base('product')} p USING(product_id) WHERE c.calendar_date IS NULL OR l.location_id IS NULL OR p.product_id IS NULL").fetchone()[0]
        out.append(ValidationResult("CAN_REFERENCES", "PASS" if count == 0 else "FAIL", table, int(count), "canonical references resolve"))
    count = con.execute(f"SELECT count(*) FROM {base('demand_forecast_weekly')} f LEFT JOIN (SELECT DISTINCT retail_year_week FROM {base('calendar_day')}) c ON f.target_retail_year_week=c.retail_year_week LEFT JOIN {base('location')} l USING(location_id) LEFT JOIN {base('product')} p USING(product_id) WHERE c.retail_year_week IS NULL OR l.location_id IS NULL OR p.product_id IS NULL OR f.forecast_created_retail_year_week>=f.target_retail_year_week OR f.forecast_created_retail_year_week%100 NOT BETWEEN 1 AND 53").fetchone()[0]
    out.append(ValidationResult("CAN_REFERENCES", "PASS" if count == 0 else "FAIL", "demand_forecast_weekly", int(count), "canonical target references and forecast ordering valid"))
    return out


def _extension_canonical_validation(con: duckdb.DuckDBPyConnection, candidate: Path, expected: dict[str, int]) -> list[ValidationResult]:
    out: list[ValidationResult] = []
    keys = {
        "company_item": "company_id,company_item_id",
        "replenishment_commitment": "retailer_order_id,order_line_number,event_version",
        "reaction_constraint": "company_id,item_scope_type_code,item_scope_id,effective_from",
        "company_item_economics": "company_id,company_item_id,effective_from",
    }
    required = {
        "company_item": {"company_id", "company_item_id", "company_item_name", "display_brand_id", "product_id", "source_company_id", "source_product_id", "effective_from"},
        "replenishment_commitment": {"retailer_order_id", "order_line_number", "event_version", "location_id", "product_id", "ordered_quantity", "invoiced_quantity", "received_quantity", "order_created_at", "status_code", "known_at"},
        "reaction_constraint": {"company_id", "item_scope_type_code", "item_scope_id", "minimum_reaction_days", "effective_from"},
        "company_item_economics": {"company_id", "company_item_id", "currency_code", "unit_cost_amount", "effective_from"},
    }
    for table, pk in keys.items():
        scan = "read_parquet('" + str(candidate / table / "*.parquet").replace("'", "''") + "')"
        description = [(row[0], row[1]) for row in con.execute(f"DESCRIBE SELECT * FROM {scan}").fetchall()]
        out.append(ValidationResult("CAN_SCHEMA_EXACT", "PASS" if description == SCHEMAS[table] else "FAIL", table, 0 if description == SCHEMAS[table] else 1, "exact canonical names, order, and types"))
        predicate = " OR ".join(f'"{name}" IS NULL' for name in sorted(required[table]))
        nulls = con.execute(f"SELECT count(*) FROM {scan} WHERE {predicate}").fetchone()[0]
        out.append(ValidationResult("CAN_REQUIRED_NULL", "PASS" if nulls == 0 else "FAIL", table, int(nulls), "required canonical values non-null"))
        count, dupes = con.execute(f"SELECT count(*),count(*)-count(DISTINCT ({pk})) FROM {scan}").fetchone()
        out.append(ValidationResult("CAN_ROW_COUNT", "PASS" if count == expected[table] else "FAIL", table, 0 if count == expected[table] else 1, "source and canonical row counts reconcile"))
        out.append(ValidationResult("CAN_PRIMARY_KEY", "PASS" if dupes == 0 else "FAIL", table, int(dupes), "canonical primary key unique"))
    base = lambda table: "read_parquet('" + str(candidate / table / "*.parquet").replace("'", "''") + "')"
    for table in ("company_item", "replenishment_commitment"):
        count = con.execute(f"SELECT count(*) FROM {base(table)} x LEFT JOIN {base('product')} p USING(product_id) " + (f"LEFT JOIN {base('location')} l USING(location_id) " if table == "replenishment_commitment" else "") + "WHERE p.product_id IS NULL" + (" OR l.location_id IS NULL" if table == "replenishment_commitment" else "")).fetchone()[0]
        out.append(ValidationResult("CAN_REFERENCES", "PASS" if count == 0 else "FAIL", table, int(count), "canonical references resolve"))
    economics_count = con.execute(f"SELECT count(*) FROM {base('company_item_economics')} e LEFT JOIN {base('company_item')} i USING(company_id,company_item_id) WHERE i.company_item_id IS NULL").fetchone()[0]
    out.append(ValidationResult("CAN_REFERENCES", "PASS" if economics_count == 0 else "FAIL", "company_item_economics", int(economics_count), "canonical economics references resolve"))
    return out


def _manifest_files(con: duckdb.DuckDBPyConnection, candidate: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(candidate.glob("*/*.parquet")):
        scan = str(path).replace("'", "''")
        rows = con.execute(f"SELECT count(*) FROM read_parquet('{scan}')").fetchone()[0]
        files.append({"path": str(path.relative_to(candidate)), "bytes": path.stat().st_size, "sha256": sha256_file(path), "rows": rows})
    return files


def ingest_release_set(manifest_path: Path, *, data_root: Path, classification: str) -> Path:
    root = _safe_data_root(data_root)
    source = inspect_release_set(manifest_path, classification)
    dataset_id = _release_set_dataset_id(release_set_identity(source))
    published = root / "canonical" / dataset_id
    run_id = "run_" + uuid.uuid4().hex
    run_root = root / "staging" / run_id
    candidate = run_root / "canonical"
    results: list[ValidationResult] = []
    try:
        results.extend(validate_release_set(source))
        _ensure_pass("source_validation", results)
        con = duckdb.connect()
        con.execute("SET preserve_insertion_order=false")
        walmart_results = validate_source_data(con, source.walmart)
        extension_results = validate_extension_data(con, source.extension, source.walmart)
        results.extend(walmart_results + extension_results)
        _ensure_pass("source_validation", walmart_results + extension_results)
        if (published / "manifest.json").is_file():
            existing = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
            intact = existing.get("dataset_id") == dataset_id and all(
                (published / entry["path"]).is_file()
                and (published / entry["path"]).stat().st_size == entry["bytes"]
                and sha256_file(published / entry["path"]) == entry["sha256"]
                for entry in existing.get("files", [])
            )
            if not intact or len(existing.get("files", [])) != 10:
                raise IngestionFailure("published_validation", [ValidationResult("PUB_IMMUTABLE_INTACT", "FAIL", count=1, summary="published dataset differs from its manifest")])
            return published
        canonicalize(con, source.walmart, candidate)
        canonicalize_extension(con, source.extension, candidate)
        walmart_expected = {MAPPING[d["dataset_name"]]: d["row_count"] for d in source.walmart.manifest["datasets"]}
        extension_expected = {MIRO_MAPPING[d["dataset_name"]]: d["row_count"] for d in source.extension.manifest["datasets"]}
        canonical_results = _canonical_validation(con, candidate, walmart_expected) + _extension_canonical_validation(con, candidate, extension_expected)
        results.extend(canonical_results)
        _ensure_pass("canonical_validation", canonical_results)
        content = {
            "dataset_id": dataset_id,
            "canonical_contract_version": CONTRACT_VERSION,
            "source_classification": classification,
            "source_release_set_id": source.manifest["release_id"],
            "source_release_set_manifest_sha256": source.manifest_sha256,
            "source_release_ids": [source.walmart.manifest["release_id"], source.extension.manifest["release_id"]],
            "source_manifests": {
                "walmart_sha256": source.walmart.manifest_sha256,
                "extension_sha256": source.extension.manifest_sha256,
            },
            "as_of": source.manifest["as_of"],
            "configuration_hash": source.manifest["configuration_hash"],
            "contract_versions": source.manifest["contract_versions"],
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "transformation_version": TRANSFORMATION_VERSION,
            "validation_contract_version": VALIDATION_VERSION,
            "dataset_mapping": {**MAPPING, **MIRO_MAPPING},
            "validation_results": [r.to_dict() for r in results if r.severity != "FAIL"],
            "files": _manifest_files(con, candidate),
        }
        (candidate / "manifest.json").write_bytes(canonical_json(content))
        (root / "canonical").mkdir(parents=True, exist_ok=True)
        os.rename(candidate, published)
        LOG.info("event=published dataset_id=%s tables=10", dataset_id)
        return published
    except Exception:
        summary = root / "quarantine" / run_id / "validation-summary.json"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_bytes(canonical_json({"run_id": run_id, "results": [r.to_dict() for r in results]}))
        LOG.error("event=failed run_id=%s failed_rules=%s", run_id, ",".join(r.rule_id for r in results if r.severity == "FAIL"))
        raise
    finally:
        if run_root.exists():
            shutil.rmtree(run_root)


def ingest(manifest_path: Path, *, data_root: Path, classification: str) -> Path:
    try:
        preview = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        preview = {}
    if isinstance(preview, dict) and {"walmart_manifest", "extension_manifest"} <= set(preview):
        return ingest_release_set(manifest_path, data_root=data_root, classification=classification)
    root = _safe_data_root(data_root)
    inventory = inspect_manifest(manifest_path, classification)
    dataset_id = _dataset_id(inventory.manifest_sha256)
    published = root / "canonical" / dataset_id
    run_id = "run_" + uuid.uuid4().hex
    run_root = root / "staging" / run_id
    candidate = run_root / "canonical"
    results: list[ValidationResult] = []
    try:
        LOG.info("event=source_validating run_id=%s adapter=%s", run_id, ADAPTER_ID)
        results.extend(validate_manifest_contract(inventory))
        _ensure_pass("source_validation", results)
        con = duckdb.connect()
        con.execute("SET preserve_insertion_order=false")
        data_results = validate_source_data(con, inventory)
        results.extend(data_results)
        _ensure_pass("source_validation", results)
        if (published / "manifest.json").is_file():
            existing = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
            intact = existing.get("dataset_id") == dataset_id and all(
                (published / entry["path"]).is_file()
                and (published / entry["path"]).stat().st_size == entry["bytes"]
                and sha256_file(published / entry["path"]) == entry["sha256"]
                for entry in existing.get("files", [])
            )
            if not intact or len(existing.get("files", [])) != 6:
                raise IngestionFailure("published_validation", [ValidationResult("PUB_IMMUTABLE_INTACT", "FAIL", count=1, summary="published dataset differs from its manifest")])
            LOG.info("event=idempotent_replay dataset_id=%s", dataset_id)
            return published
        raw = root / "raw" / inventory.manifest_sha256
        raw.mkdir(parents=True, exist_ok=True)
        ref = raw / "source-reference.json"
        if not ref.exists():
            ref.write_bytes(canonical_json({"manifest_path":str(inventory.manifest_path),"manifest_sha256":inventory.manifest_sha256,"release_id":inventory.manifest["release_id"],"classification":classification,"receipt_time":datetime.now(timezone.utc).isoformat(),"file_inventory_sha256":hashlib.sha256(canonical_json([{"path":f.path,"bytes":f.bytes,"sha256":f.sha256} for f in inventory.files])).hexdigest()}))
        LOG.info("event=canonicalizing run_id=%s dataset_id=%s", run_id, dataset_id)
        canonicalize(con, inventory, candidate)
        expected = {MAPPING[d["dataset_name"]]: d["row_count"] for d in inventory.manifest["datasets"]}
        canonical_results = _canonical_validation(con, candidate, expected)
        results.extend(canonical_results)
        _ensure_pass("canonical_validation", canonical_results)
        files = []
        for path in sorted(candidate.glob("*/*.parquet")):
            table = path.parent.name
            scan = str(path).replace("'", "''")
            rows = con.execute(f"SELECT count(*) FROM read_parquet('{scan}')").fetchone()[0]
            if table in {"calendar_day"}:
                lo, hi = con.execute(f"SELECT min(calendar_date),max(calendar_date) FROM read_parquet('{scan}')").fetchone()
                bounds = {"minimum_date":str(lo),"maximum_date":str(hi)}
            elif table in {"sales_daily", "inventory_daily"}:
                lo, hi = con.execute(f"SELECT min(business_date),max(business_date) FROM read_parquet('{scan}')").fetchone()
                bounds = {"minimum_date":str(lo),"maximum_date":str(hi)}
            elif table == "demand_forecast_weekly":
                lo, hi = con.execute(f"SELECT min(target_retail_year_week),max(target_retail_year_week) FROM read_parquet('{scan}')").fetchone()
                bounds = {"minimum_retail_year_week":lo,"maximum_retail_year_week":hi}
            else:
                bounds = {}
            files.append({"path":str(path.relative_to(candidate)),"bytes":path.stat().st_size,"sha256":sha256_file(path),"rows":rows,**bounds})
        release_manifest = {"dataset_id":dataset_id,"canonical_contract_version":CONTRACT_VERSION,"source_classification":classification,"source":{"manifest_path":str(inventory.manifest_path),"manifest_sha256":inventory.manifest_sha256,"release_id":inventory.manifest["release_id"],"as_of":inventory.manifest["as_of"]},"adapter":{"id":ADAPTER_ID,"version":ADAPTER_VERSION},"transformation_version":TRANSFORMATION_VERSION,"validation_contract_version":VALIDATION_VERSION,"dataset_mapping":MAPPING,"validation_results":[r.to_dict() for r in results if r.severity != "FAIL"],"files":files}
        (candidate / "manifest.json").write_bytes(canonical_json(release_manifest))
        (root / "canonical").mkdir(parents=True, exist_ok=True)
        try:
            os.rename(candidate, published)
        except FileExistsError:
            if not (published / "manifest.json").is_file():
                raise
        LOG.info("event=published run_id=%s dataset_id=%s tables=6", run_id, dataset_id)
        return published
    except Exception:
        summary = root / "quarantine" / run_id / "validation-summary.json"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_bytes(canonical_json({"run_id":run_id,"results":[r.to_dict() for r in results]}))
        LOG.error("event=failed run_id=%s failed_rules=%s", run_id, ",".join(r.rule_id for r in results if r.severity == "FAIL"))
        raise
    finally:
        if run_root.exists():
            shutil.rmtree(run_root)
