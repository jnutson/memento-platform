from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .models import IngestionFailure, SourceFile, SourceInventory, ValidationResult


REQUIRED_DATASETS = {
    "calendar_dim",
    "store_dim",
    "omni_item_dimensions",
    "store_sales",
    "store_invt",
    "long_rng_store_dmd_frcst",
}
PARTITIONED_DATASETS = {"store_sales", "store_invt", "long_rng_store_dmd_frcst"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RELEASE_ID = re.compile(r"^[0-9a-f]{16}-[0-9]{8}T[0-9]{6}Z$")


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def dataset_tree_sha256(files: list[SourceFile], dataset: str) -> str:
    digest = hashlib.sha256()
    prefix = dataset + "/"
    for source in sorted((f for f in files if f.path.startswith(prefix)), key=lambda f: f.path):
        digest.update(source.path.removeprefix(prefix).encode())
        digest.update(bytes.fromhex(source.sha256))
    return digest.hexdigest()


def _fail(rule: str, summary: str, dataset: str | None = None, count: int = 1) -> None:
    raise IngestionFailure("source_validation", [ValidationResult(rule, "FAIL", dataset, count, summary)])


def inspect_manifest(path: Path, classification: str) -> SourceInventory:
    if not path.is_absolute():
        _fail("SRC_PATH_EXPLICIT", "manifest path must be absolute")
    try:
        info = path.lstat()
    except FileNotFoundError:
        _fail("SRC_MANIFEST_EXISTS", "manifest does not exist")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail("SRC_MANIFEST_REGULAR", "manifest must be a non-symlink regular file")
    if path.resolve(strict=True) != path:
        _fail("SRC_MANIFEST_SYMLINK_COMPONENT", "manifest path must not contain symlink components")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("SRC_MANIFEST_JSON", "manifest is not valid UTF-8 JSON")
    if not isinstance(manifest, dict):
        _fail("SRC_MANIFEST_SHAPE", "manifest root must be an object")
    root = path.parent.resolve(strict=True)
    files: list[SourceFile] = []
    seen: set[str] = set()
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        _fail("SRC_FILE_INVENTORY", "files must be an array")
    for entry in raw_files:
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}:
            _fail("SRC_FILE_ENTRY", "file inventory entry has invalid fields")
        rel = entry["path"]
        if not isinstance(rel, str):
            _fail("SRC_FILE_PATH", "file path must be a string")
        pure = PurePosixPath(rel)
        if pure.is_absolute() or not pure.parts or any(p in {"", ".", ".."} for p in pure.parts):
            _fail("SRC_FILE_PATH", "file path is unsafe")
        if rel in seen:
            _fail("SRC_FILE_DUPLICATE", "duplicate file path")
        seen.add(rel)
        candidate = root.joinpath(*pure.parts)
        try:
            st = candidate.lstat()
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            _fail("SRC_FILE_EXISTS", "declared file is missing")
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            _fail("SRC_FILE_REGULAR", "declared input is not a regular file")
        current = root
        for part in pure.parts[:-1]:
            current = current / part
            if current.is_symlink():
                _fail("SRC_FILE_SYMLINK_COMPONENT", "declared input path contains a symlink directory")
        try:
            resolved.relative_to(root)
        except ValueError:
            _fail("SRC_FILE_ESCAPE", "declared input escapes release root")
        size, digest = entry["bytes"], entry["sha256"]
        if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or not HEX64.fullmatch(digest):
            _fail("SRC_FILE_METADATA", "invalid file size or digest")
        files.append(SourceFile(rel, resolved, size, digest))
    return SourceInventory(path, sha256_file(path), root, manifest, tuple(files), classification)


def validate_manifest_contract(inventory: SourceInventory, *, now: datetime | None = None) -> list[ValidationResult]:
    m = inventory.manifest
    results: list[ValidationResult] = []

    def check(ok: bool, rule: str, summary: str, dataset: str | None = None, count: int = 0) -> None:
        results.append(ValidationResult(rule, "PASS" if ok else "FAIL", dataset, 0 if ok else max(1, count), summary))

    check(m.get("manifest_schema_version") == "1.0.0", "SRC_MANIFEST_VERSION", "supported manifest schema")
    check(m.get("dataset_type") == "observable", "SRC_DATASET_TYPE", "observable release required")
    check(isinstance(m.get("release_id"), str) and bool(RELEASE_ID.fullmatch(str(m.get("release_id")))), "SRC_RELEASE_ID", "valid release identity")
    gates = m.get("release_gates")
    check(isinstance(gates, dict) and bool(gates) and all(v is True for v in gates.values()), "SRC_RELEASE_GATES", "all release gates true")
    datasets = m.get("datasets")
    if not isinstance(datasets, list):
        check(False, "SRC_DATASETS", "datasets must be an array")
        return results
    names = [d.get("dataset_name") for d in datasets if isinstance(d, dict)]
    check(len(names) == len(datasets) and len(set(names)) == len(names), "SRC_DATASET_DUPLICATE", "dataset names unique")
    check(set(names) == REQUIRED_DATASETS, "SRC_DATASET_SET", "exact required dataset set")
    for d in datasets:
        if not isinstance(d, dict):
            continue
        name = str(d.get("dataset_name"))
        check(d.get("classification") == "observable", "SRC_CLASSIFICATION", "observable dataset required", name)
        check(d.get("schema_version") == "1.0.0", "SRC_SCHEMA_VERSION", "supported physical schema", name)
        declared = [f for f in inventory.files if f.path.startswith(name + "/")]
        check(d.get("file_count") == len(declared), "SRC_FILE_COUNT", "manifest file count reconciles", name)
        check(isinstance(d.get("row_count"), int) and d.get("row_count", -1) >= 0, "SRC_ROW_COUNT_DECLARED", "valid declared row count", name)
        expected_partitions = ["wm_yr_wk_nbr", "store_shard"] if name in PARTITIONED_DATASETS else []
        check(d.get("partition_columns") == expected_partitions, "SRC_PARTITION_CONTRACT", "declared partition contract", name)
        if name in PARTITIONED_DATASETS:
            layout_ok = all(re.fullmatch(rf"{name}/wm_yr_wk_nbr=[0-9]{{6}}/part-shard-[0-9]{{4}}\.parquet", f.path) for f in declared)
        else:
            layout_ok = all(re.fullmatch(rf"{name}/part-[0-9]{{5}}\.parquet", f.path) for f in declared)
        check(layout_ok, "SRC_PARTITION_LAYOUT", "partition path matches declared layout", name)
    top_dirs = {f.path.split("/", 1)[0] for f in inventory.files}
    check(top_dirs == REQUIRED_DATASETS, "SRC_FILE_DATASET_SET", "file inventory maps to required datasets")
    physical = {str(p.relative_to(inventory.root).as_posix()) for p in inventory.root.rglob("*.parquet") if p.is_file()}
    check(physical == {f.path for f in inventory.files}, "SRC_FILE_INVENTORY_EXACT", "declared and physical Parquet inventory match")
    for source in inventory.files:
        check(source.absolute_path.stat().st_size == source.bytes, "SRC_FILE_BYTES", "file size matches", source.path)
        check(sha256_file(source.absolute_path) == source.sha256, "SRC_FILE_HASH", "file hash matches", source.path)
    for d in datasets:
        if isinstance(d, dict) and d.get("dataset_name") in REQUIRED_DATASETS:
            name = str(d["dataset_name"])
            check(d.get("sha256") == dataset_tree_sha256(list(inventory.files), name), "SRC_DATASET_TREE_HASH", "dataset tree hash matches", name)
    try:
        as_of = datetime.fromisoformat(str(m["as_of"]).replace("Z", "+00:00"))
        valid_as_of = as_of.tzinfo is not None
    except (KeyError, ValueError, TypeError):
        valid_as_of = False
        as_of = datetime.max.replace(tzinfo=timezone.utc)
    check(valid_as_of, "SRC_AS_OF", "valid timezone-aware as_of")
    clock = now or datetime.now(timezone.utc)
    check(inventory.classification == "synthetic" or as_of <= clock, "SRC_FUTURE_AS_OF", "future as_of allowed only for trusted synthetic classification")
    return results
