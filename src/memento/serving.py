from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path, PurePosixPath

import duckdb

from .manifest import sha256_file


PREDICTION_ID = re.compile(r"^oos_[0-9a-f]{64}$")
SIGNAL_ID = re.compile(r"^sig_[0-9a-f]{64}$")


class PredictionStore:
    """Read-only boundary for API adapters over immutable prediction Parquet."""

    def __init__(self, predictions_root: Path, canonical_root: Path | None = None):
        self.root = predictions_root.resolve(strict=True)
        candidate = canonical_root if canonical_root is not None else self.root.parent / "canonical"
        self.canonical_root = candidate.resolve()

    @staticmethod
    def _safe_member(root: Path, reference: object) -> Path:
        if not isinstance(reference, str):
            raise ValueError("invalid manifest path")
        pure = PurePosixPath(reference)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError("unsafe manifest path")
        path = root.joinpath(*pure.parts).resolve(strict=True)
        path.relative_to(root)
        return path

    @staticmethod
    def _validate_files(root: Path, manifest: dict[str, object]) -> None:
        files = manifest.get("files")
        if not isinstance(files, list):
            raise ValueError("invalid file inventory")
        for item in files:
            if not isinstance(item, dict):
                raise ValueError("invalid file inventory")
            file = PredictionStore._safe_member(root, item.get("path"))
            if (
                not file.is_file()
                or file.is_symlink()
                or file.stat().st_size != item.get("bytes")
                or sha256_file(file) != item.get("sha256")
            ):
                raise ValueError("release integrity failure")

    def current_release(self) -> tuple[Path, dict[str, object]]:
        pointer = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        reference = pointer.get("manifest")
        if not isinstance(reference, str):
            raise ValueError("invalid prediction pointer")
        manifest_path = self._safe_member(self.root, reference)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("invalid prediction manifest")
        if manifest.get("prediction_set_id") != pointer.get("prediction_set_id"):
            raise ValueError("prediction pointer identity mismatch")
        release = manifest_path.parent
        self._validate_files(release, manifest)
        return release, manifest

    def canonical_release(self, prediction_manifest: dict[str, object]) -> tuple[Path, dict[str, object]]:
        dataset_id = prediction_manifest.get("canonical_dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id.startswith("mds_"):
            raise ValueError("invalid canonical dataset identity")
        release = (self.canonical_root / dataset_id).resolve(strict=True)
        release.relative_to(self.canonical_root)
        manifest_path = release / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("canonical manifest missing or unsafe")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("dataset_id") != dataset_id:
            raise ValueError("canonical dataset identity mismatch")
        self._validate_files(release, manifest)
        return release, manifest

    def _table_files(self, release: Path, manifest: dict[str, object], table: str) -> list[str]:
        prefix = f"{table}/"
        files = [
            str(self._safe_member(release, item.get("path")))
            for item in manifest.get("files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].startswith(prefix)
        ]
        if not files:
            raise ValueError(f"canonical {table} dataset missing")
        return files

    def run(self) -> dict[str, object]:
        _, manifest = self.current_release()
        return manifest

    def top_predictions(self, limit: int = 10) -> list[dict[str, object]]:
        if not 1 <= limit <= 10:
            raise ValueError("limit must be between 1 and 10")
        release, _ = self.current_release()
        rows = duckdb.connect().execute(
            "SELECT * FROM read_parquet(?) WHERE is_top_10 ORDER BY rank_position LIMIT ?",
            [str(release / "oos_prediction.parquet"), limit],
        ).to_arrow_table()
        return rows.to_pylist()

    def prediction(self, prediction_id: str) -> dict[str, object] | None:
        self._validate_prediction_id(prediction_id)
        release, _ = self.current_release()
        rows = duckdb.connect().execute(
            "SELECT * FROM read_parquet(?) WHERE prediction_id=? AND is_top_10 LIMIT 1",
            [str(release / "oos_prediction.parquet"), prediction_id],
        ).to_arrow_table().to_pylist()
        return rows[0] if rows else None

    @staticmethod
    def _validate_prediction_id(prediction_id: str) -> None:
        if not PREDICTION_ID.fullmatch(prediction_id):
            raise ValueError("invalid prediction identity")

    def evidence(self, prediction_id: str) -> list[dict[str, object]]:
        self._validate_prediction_id(prediction_id)
        release, _ = self.current_release()
        rows = duckdb.connect().execute(
            "SELECT * FROM read_parquet(?) WHERE prediction_id=? ORDER BY projection_date,path",
            [str(release / "oos_prediction_evidence.parquet"), prediction_id],
        ).to_arrow_table()
        return rows.to_pylist()

    def display_identities(self, predictions: list[dict[str, object]]) -> dict[str, dict[str, str]]:
        _, prediction_manifest = self.current_release()
        canonical, canonical_manifest = self.canonical_release(prediction_manifest)
        company_files = self._table_files(canonical, canonical_manifest, "company_item")
        location_files = self._table_files(canonical, canonical_manifest, "location")
        con = duckdb.connect()
        result: dict[str, dict[str, str]] = {}
        for prediction in predictions:
            prediction_id = prediction.get("prediction_id")
            prediction_date = prediction.get("prediction_date")
            if not isinstance(prediction_id, str) or not isinstance(prediction_date, date):
                raise ValueError("invalid prediction identity or date")
            item = con.execute(
                """SELECT company_item_name,company_item_id,source_product_id
                   FROM read_parquet(?)
                   WHERE product_id=? AND company_id=? AND effective_from<=?
                     AND (effective_to IS NULL OR effective_to>=?)
                   ORDER BY effective_from DESC LIMIT 1""",
                [company_files, prediction.get("product_id"), prediction.get("company_id"), prediction_date, prediction_date],
            ).fetchone()
            location = con.execute(
                """SELECT location_name,source_location_id
                   FROM read_parquet(?) WHERE location_id=? LIMIT 1""",
                [location_files, prediction.get("store_id")],
            ).fetchone()
            if item is None or location is None:
                raise ValueError("prediction display identity missing")
            result[prediction_id] = {
                "item_name": item[0],
                "company_item_id": item[1],
                "source_product_id": item[2],
                "store_name": location[0],
                "source_location_id": location[1],
            }
        return result

    def display_identity(self, prediction: dict[str, object]) -> dict[str, str]:
        prediction_id = prediction.get("prediction_id")
        if not isinstance(prediction_id, str):
            raise ValueError("invalid prediction identity")
        return self.display_identities([prediction])[prediction_id]


class SignalStore:
    """Read-only boundary over immutable unified signal releases."""

    def __init__(self, signals_root: Path, canonical_root: Path):
        self.root = signals_root.resolve(strict=True)
        self.canonical_root = canonical_root.resolve(strict=True)

    def current_release(self) -> tuple[Path, dict[str, object]]:
        pointer = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        if not isinstance(pointer, dict):
            raise ValueError("invalid signal pointer")
        manifest_path = PredictionStore._safe_member(self.root, pointer.get("manifest"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("invalid signal manifest")
        if manifest.get("signal_set_id") != pointer.get("signal_set_id"):
            raise ValueError("signal pointer identity mismatch")
        files = manifest.get("files")
        if not isinstance(files, list) or {item.get("path") for item in files if isinstance(item, dict)} != {"signal.parquet", "signal_evidence.parquet"}:
            raise ValueError("invalid signal file inventory")
        PredictionStore._validate_files(manifest_path.parent, manifest)
        return manifest_path.parent, manifest

    def run(self) -> dict[str, object]:
        return self.current_release()[1]

    def top_signals(self, signal_type: str | None = None) -> list[dict[str, object]]:
        if signal_type is not None and signal_type not in {"availability", "demand_momentum", "inventory_imbalance"}:
            raise ValueError("invalid signal type")
        release, _ = self.current_release()
        predicate = "WHERE is_overall_top_10" + (" AND signal_type=?" if signal_type else "")
        params: list[object] = [str(release / "signal.parquet")]
        if signal_type: params.append(signal_type)
        return duckdb.connect().execute(f"SELECT * FROM read_parquet(?) {predicate} ORDER BY overall_rank_position", params).to_arrow_table().to_pylist()

    def signal(self, signal_id: str) -> dict[str, object] | None:
        if not SIGNAL_ID.fullmatch(signal_id):
            raise ValueError("invalid signal identity")
        release, _ = self.current_release()
        rows = duckdb.connect().execute("SELECT * FROM read_parquet(?) WHERE signal_id=? AND is_overall_top_10", [str(release / "signal.parquet"), signal_id]).to_arrow_table().to_pylist()
        return rows[0] if rows else None

    def evidence(self, signal_id: str) -> list[dict[str, object]]:
        if not SIGNAL_ID.fullmatch(signal_id):
            raise ValueError("invalid signal identity")
        release, _ = self.current_release()
        return duckdb.connect().execute("SELECT * FROM read_parquet(?) WHERE signal_id=? ORDER BY evidence_date,evidence_type,path", [str(release / "signal_evidence.parquet"), signal_id]).to_arrow_table().to_pylist()

    def display_identities(self, signals: list[dict[str, object]]) -> dict[str, dict[str, str]]:
        _, manifest = self.current_release()
        dataset_id = manifest.get("canonical_dataset_id")
        canonical = (self.canonical_root / str(dataset_id)).resolve(strict=True)
        canonical.relative_to(self.canonical_root)
        canonical_manifest = json.loads((canonical / "manifest.json").read_text())
        PredictionStore._validate_files(canonical, canonical_manifest)
        con = duckdb.connect()
        result = {}
        for signal in signals:
            item = con.execute("SELECT company_item_name,company_item_id,source_product_id FROM read_parquet(?) WHERE product_id=? AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) LIMIT 1", [str(canonical / "company_item" / "*.parquet"), signal["product_id"], signal["observation_date"], signal["observation_date"]]).fetchone()
            location = con.execute("SELECT location_name,source_location_id FROM read_parquet(?) WHERE location_id=? LIMIT 1", [str(canonical / "location" / "*.parquet"), signal["store_id"]]).fetchone()
            if item is None or location is None:
                raise ValueError("signal display identity missing")
            result[str(signal["signal_id"])] = {"item_name": item[0], "company_item_id": item[1], "source_product_id": item[2], "store_name": location[0], "source_location_id": location[1]}
        return result
