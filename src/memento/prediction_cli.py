from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .models import IngestionFailure
from .prediction import run_predictions


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish deterministic Miro Toys OOS predictions")
    parser.add_argument("canonical_release", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        output = run_predictions(args.canonical_release, data_root=args.data_root)
    except IngestionFailure as exc:
        logging.error("phase=%s failed_rules=%s", exc.phase, ",".join(result.rule_id for result in exc.results if result.severity == "FAIL"))
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
