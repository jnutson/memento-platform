from __future__ import annotations

import argparse
from pathlib import Path

from .evaluation import evaluate_predictions


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a matured immutable OOS prediction set")
    parser.add_argument("prediction_release", type=Path)
    parser.add_argument("later_canonical_release", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    print(evaluate_predictions(args.prediction_release, args.later_canonical_release, data_root=args.data_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
