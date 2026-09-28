from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


Severity = Literal["PASS", "WARN", "FAIL"]


@dataclass(frozen=True)
class ValidationResult:
    rule_id: str
    severity: Severity
    dataset: str | None = None
    count: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class IngestionFailure(RuntimeError):
    def __init__(self, phase: str, results: list[ValidationResult]):
        self.phase = phase
        self.results = results
        failed = [r.rule_id for r in results if r.severity == "FAIL"]
        super().__init__(f"{phase} failed rules={','.join(failed)}")


@dataclass(frozen=True)
class SourceFile:
    path: str
    absolute_path: Path
    bytes: int
    sha256: str


@dataclass(frozen=True)
class SourceInventory:
    manifest_path: Path
    manifest_sha256: str
    root: Path
    manifest: dict[str, object]
    files: tuple[SourceFile, ...]
    classification: str
