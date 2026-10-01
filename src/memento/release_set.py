from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .manifest import HEX64, canonical_json, sha256_file
from .models import IngestionFailure, SourceInventory, ValidationResult


WALMART_DATASETS = {
    "calendar_dim", "store_dim", "omni_item_dimensions", "store_sales",
    "store_invt", "long_rng_store_dmd_frcst",
}
EXTENSION_DATASETS = {
    "dim_item", "retailer_replenishment_commitment", "item_reaction_constraint",
}
EXPECTED_CONTRACT_VERSIONS = {
    "product": "miro-oos-product-v1.6.0",
    "metrics": "miro-oos-metrics-v1.6.0",
    "data_scope": "miro-oos-data-scope-v1.6.0",
    "glossary": "memento-glossary-v1.3.0",
}
RELEASE_ID = re.compile(r"^[0-9a-f]{16}-[0-9]{8}T[0-9]{6}Z$")


@dataclass(frozen=True)
class ReleaseSetInventory:
    manifest_path: Path
    manifest_sha256: str
    manifest: dict[str, object]
    walmart: SourceInventory
    extension: SourceInventory


def _failure(rule: str, summary: str) -> None:
    raise IngestionFailure(
        "source_validation", [ValidationResult(rule, "FAIL", count=1, summary=summary)]
    )


def _regular_json(path: Path, rule_prefix: str) -> dict[str, object]:
    if not path.is_absolute():
        _failure(f"{rule_prefix}_PATH_EXPLICIT", "manifest path must be absolute")
    try:
        info = path.lstat()
    except FileNotFoundError:
        _failure(f"{rule_prefix}_EXISTS", "manifest does not exist")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _failure(f"{rule_prefix}_REGULAR", "manifest must be a non-symlink regular file")
    if path.resolve(strict=True) != path:
        _failure(f"{rule_prefix}_SYMLINK_COMPONENT", "manifest path has a symlink component")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _failure(f"{rule_prefix}_JSON", "manifest is not valid UTF-8 JSON")
    if not isinstance(value, dict):
        _failure(f"{rule_prefix}_SHAPE", "manifest root must be an object")
    return value


def _safe_reference(root: Path, value: object, rule: str) -> Path:
    if not isinstance(value, str):
        _failure(rule, "package manifest reference must be a string")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(p in {"", ".", ".."} for p in pure.parts):
        _failure(rule, "package manifest reference must be safe and relative")
    candidate = root.joinpath(*pure.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError):
        _failure(rule, "package manifest reference escapes or is missing")
    return resolved


def _package_inventory(path: Path, manifest: dict[str, object], classification: str) -> SourceInventory:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        _failure("SET_PACKAGE_DATASETS", "package datasets must be an array")
    root = path.parent
    files = []
    from .models import SourceFile

    for dataset in datasets:
        if not isinstance(dataset, dict) or not isinstance(dataset.get("dataset_name"), str):
            _failure("SET_PACKAGE_DATASET", "invalid package dataset entry")
        name = dataset["dataset_name"]
        folder = root / name
        if not folder.is_dir() or folder.is_symlink():
            _failure("SET_PACKAGE_DIRECTORY", "declared dataset directory is missing or unsafe")
        physical = sorted(p for p in folder.rglob("*.parquet") if p.is_file())
        if len(physical) != dataset.get("file_count"):
            _failure("SET_PACKAGE_FILE_COUNT", "declared package file count does not reconcile")
        tree = __import__("hashlib").sha256()
        for item in physical:
            if item.is_symlink() or item.resolve(strict=True) != item:
                _failure("SET_PACKAGE_FILE_REGULAR", "package contains a symlinked file")
            try:
                item.resolve(strict=True).relative_to(root.resolve(strict=True))
            except ValueError:
                _failure("SET_PACKAGE_FILE_ESCAPE", "package file escapes package root")
            digest = sha256_file(item)
            rel_dataset = item.relative_to(folder).as_posix()
            tree.update(rel_dataset.encode())
            tree.update(bytes.fromhex(digest))
            files.append(SourceFile(item.relative_to(root).as_posix(), item, item.stat().st_size, digest))
        if dataset.get("sha256") != tree.hexdigest():
            _failure("SET_PACKAGE_TREE_HASH", "dataset tree hash does not match")
    top = {f.path.split("/", 1)[0] for f in files}
    names = {str(d["dataset_name"]) for d in datasets if isinstance(d, dict)}
    if top != names:
        _failure("SET_PACKAGE_FILE_SET", "physical package files do not match dataset declarations")
    all_physical = {p.resolve(strict=True) for p in root.rglob("*.parquet") if p.is_file()}
    if all_physical != {f.absolute_path.resolve(strict=True) for f in files}:
        _failure("SET_PACKAGE_FILE_SET", "package contains undeclared Parquet files")
    return SourceInventory(path, sha256_file(path), root, manifest, tuple(files), classification)


def inspect_release_set(path: Path, classification: str) -> ReleaseSetInventory:
    manifest = _regular_json(path, "SET_MANIFEST")
    # Release-set references are relative to the configured release root, two levels
    # above release-sets/<release-id>/manifest.json.
    if path.parent.parent.name != "release-sets":
        _failure("SET_LAYOUT", "release-set manifest must be under release-sets/<release-id>")
    release_root = path.parent.parent.parent.resolve(strict=True)
    wm_path = _safe_reference(release_root, manifest.get("walmart_manifest"), "SET_WALMART_PATH")
    ext_path = _safe_reference(release_root, manifest.get("extension_manifest"), "SET_EXTENSION_PATH")
    wm_manifest = _regular_json(wm_path, "SET_WALMART_MANIFEST")
    ext_manifest = _regular_json(ext_path, "SET_EXTENSION_MANIFEST")
    return ReleaseSetInventory(
        path, sha256_file(path), manifest,
        _package_inventory(wm_path, wm_manifest, classification),
        _package_inventory(ext_path, ext_manifest, classification),
    )


def validate_release_set(inventory: ReleaseSetInventory, *, now: datetime | None = None) -> list[ValidationResult]:
    s, wm, ext = inventory.manifest, inventory.walmart.manifest, inventory.extension.manifest
    out: list[ValidationResult] = []

    def check(ok: bool, rule: str, summary: str, dataset: str | None = None) -> None:
        out.append(ValidationResult(rule, "PASS" if ok else "FAIL", dataset, 0 if ok else 1, summary))

    check(s.get("manifest_schema_version") == "1.0.0", "SET_MANIFEST_VERSION", "supported release-set manifest")
    release_id = s.get("release_id")
    check(isinstance(release_id, str) and bool(RELEASE_ID.fullmatch(release_id)), "SET_RELEASE_ID", "valid release-set identity")
    check(wm.get("release_id") == release_id == ext.get("release_id"), "SET_RELEASE_BINDING", "package release identities match")
    check(s.get("walmart_manifest_sha256") == inventory.walmart.manifest_sha256, "SET_WALMART_HASH", "Walmart manifest checksum matches")
    check(s.get("extension_manifest_sha256") == inventory.extension.manifest_sha256, "SET_EXTENSION_HASH", "extension manifest checksum matches")
    check(ext.get("source_walmart_manifest_sha256") == inventory.walmart.manifest_sha256, "SET_EXTENSION_BINDING", "extension binds exact Walmart manifest")
    check(s.get("as_of") == wm.get("as_of"), "SET_CUTOFF_BINDING", "release-set and Walmart cutoff match")
    check(s.get("configuration_hash") == wm.get("configuration_hash") == ext.get("configuration_hash"), "SET_CONFIGURATION_BINDING", "configuration hashes match")
    check(s.get("contract_versions") == wm.get("contract_versions") == ext.get("contract_versions"), "SET_CONTRACT_BINDING", "controlling contract versions match")
    check(s.get("contract_versions") == EXPECTED_CONTRACT_VERSIONS, "SET_CONTRACT_VERSIONS", "accepted controlling contract versions")
    wm_names = {d.get("dataset_name") for d in wm.get("datasets", []) if isinstance(d, dict)}
    ext_names = {d.get("dataset_name") for d in ext.get("datasets", []) if isinstance(d, dict)}
    check(wm_names == WALMART_DATASETS, "SET_WALMART_DATASETS", "exact six Walmart datasets")
    check(ext_names == EXTENSION_DATASETS, "SET_EXTENSION_DATASETS", "exact three Miro datasets")
    check(wm.get("dataset_type") == "observable", "SET_WALMART_OBSERVABLE", "Walmart package is observable")
    check(isinstance(ext.get("po_retention_days"), int) and ext.get("po_retention_days") == 56, "SET_PO_RETENTION", "declared 56-day PO retention")
    try:
        as_of = datetime.fromisoformat(str(s["as_of"]).replace("Z", "+00:00"))
        valid = as_of.tzinfo is not None
    except (KeyError, TypeError, ValueError):
        as_of, valid = datetime.max.replace(tzinfo=timezone.utc), False
    check(valid, "SET_AS_OF", "valid timezone-aware cutoff")
    check(classification_is_future_safe(inventory.walmart.classification, as_of, now), "SET_FUTURE_AS_OF", "future cutoff allowed only for synthetic data")
    return out


def classification_is_future_safe(classification: str, as_of: datetime, now: datetime | None) -> bool:
    return classification == "synthetic" or as_of <= (now or datetime.now(timezone.utc))


def release_set_identity(inventory: ReleaseSetInventory) -> bytes:
    return canonical_json({
        "release_set_manifest_sha256": inventory.manifest_sha256,
        "walmart_manifest_sha256": inventory.walmart.manifest_sha256,
        "extension_manifest_sha256": inventory.extension.manifest_sha256,
    })
