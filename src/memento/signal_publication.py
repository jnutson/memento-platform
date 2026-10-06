from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .manifest import canonical_json, sha256_file
from .models import IngestionFailure, ValidationResult
from .signal_contract import EVIDENCE_SCHEMA, SIGNAL_CONTRACT_VERSION, SIGNAL_PUBLICATION_VERSION, SIGNAL_RANKER_VERSION, SIGNAL_SCHEMA, SIGNAL_TYPE_ORDER


def publish_signal_set(
    candidates: list[dict[str, object]], evidence: list[dict[str, object]], *,
    canonical_manifest: dict[str, object], data_root: Path, configuration: dict[str, object],
    reason_codes: list[str] | None = None,
) -> Path:
    config_hash = hashlib.sha256(canonical_json(configuration)).hexdigest()
    identity = {
        "canonical_dataset_id": canonical_manifest["dataset_id"],
        "source_manifest_hashes": canonical_manifest.get("source_manifests", {}),
        "signal_as_of": canonical_manifest["as_of"], "metric_contract_version": SIGNAL_CONTRACT_VERSION,
        "signal_publication_version": SIGNAL_PUBLICATION_VERSION, "ranker_version": SIGNAL_RANKER_VERSION,
        "configuration_hash": config_hash,
    }
    signal_set_id = "mss_" + hashlib.sha256(canonical_json(identity)).hexdigest()
    root = data_root.resolve() / "signals"
    published = root / signal_set_id
    if (published / "manifest.json").is_file():
        manifest = json.loads((published / "manifest.json").read_text())
        files = manifest.get("files") if isinstance(manifest, dict) else None
        expected_paths = {"signal.parquet", "signal_evidence.parquet"}
        intact = (
            isinstance(manifest, dict)
            and manifest.get("signal_set_id") == signal_set_id
            and all(manifest.get(key) == value for key, value in identity.items())
            and isinstance(files, list)
            and {item.get("path") for item in files if isinstance(item, dict)} == expected_paths
            and all(
                isinstance(item, dict)
                and (published / str(item["path"])).is_file()
                and (published / str(item["path"])).stat().st_size == item.get("bytes")
                and sha256_file(published / str(item["path"])) == item.get("sha256")
                for item in files
            )
        )
        if intact:
            return published
        raise IngestionFailure("published_validation", [ValidationResult("SIGNAL_IMMUTABLE_INTACT", "FAIL", count=1, summary="published signal set differs from manifest")])
    required_rank_fields = {"impact_score", "rank_score", "signal_type_rank_position", "overall_rank_position", "is_overall_top_10"}
    if any(not required_rank_fields <= row.keys() for row in candidates):
        raise ValueError("signal publication requires pre-ranked candidates")
    for row in candidates:
        row.update(metric_contract_version=SIGNAL_CONTRACT_VERSION, signal_publication_version=SIGNAL_PUBLICATION_VERSION, ranker_version=SIGNAL_RANKER_VERSION, configuration_hash=config_hash)
    stage = data_root.resolve() / "staging" / ("run_" + uuid.uuid4().hex) / "signals"
    try:
        stage.mkdir(parents=True)
        files = []
        for name, rows, schema in (("signal.parquet", candidates, SIGNAL_SCHEMA), ("signal_evidence.parquet", evidence, EVIDENCE_SCHEMA)):
            target = stage / name
            table = pa.Table.from_pylist(rows, schema=schema)
            pq.write_table(table, target, compression="zstd", row_group_size=122_880)
            files.append({"path": name, "bytes": target.stat().st_size, "sha256": sha256_file(target), "rows": table.num_rows})
        counts = {name: sum(row["signal_type"] == name for row in candidates) for name in SIGNAL_TYPE_ORDER}
        diagnostics = {code: (reason_codes or []).count(code) for code in sorted(set(reason_codes or []))}
        manifest = {"signal_set_id": signal_set_id, **identity, "source_release_set_id": canonical_manifest["source_release_set_id"], "source_release_ids": canonical_manifest["source_release_ids"], "candidate_count": len(candidates), "display_count": min(len(candidates), 10), "candidate_counts_by_type": counts, "reason_code_counts": diagnostics, "configuration": configuration, "files": files}
        (stage / "manifest.json").write_bytes(canonical_json(manifest))
        root.mkdir(parents=True, exist_ok=True)
        os.rename(stage, published)
        pointer = root / (".current-" + uuid.uuid4().hex + ".tmp")
        pointer.write_bytes(canonical_json({"signal_set_id": signal_set_id, "manifest": f"{signal_set_id}/manifest.json"}))
        os.replace(pointer, root / "current.json")
        return published
    finally:
        run_root = stage.parent
        if run_root.exists():
            shutil.rmtree(run_root)
