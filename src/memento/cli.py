from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .models import IngestionFailure
from .orchestrator import ingest


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a Walmart observable release as Memento Retail V1")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--classification", required=True, choices=("synthetic", "internal"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        path = ingest(args.manifest, data_root=args.data_root, classification=args.classification)
    except IngestionFailure as exc:
        logging.error("phase=%s failed_rules=%s", exc.phase, ",".join(r.rule_id for r in exc.results if r.severity == "FAIL"))
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
