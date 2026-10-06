from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from .signals import run_signals


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish an immutable Memento Signal set")
    parser.add_argument("canonical_root", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--annual-carrying-cost-rate", type=Decimal, required=True)
    parser.add_argument("--carrying-rate-version", required=True)
    args = parser.parse_args()
    print(run_signals(args.canonical_root, data_root=args.data_root, annual_carrying_cost_rate=args.annual_carrying_cost_rate, carrying_rate_version=args.carrying_rate_version))


if __name__ == "__main__":
    main()
