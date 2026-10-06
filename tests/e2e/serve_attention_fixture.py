from __future__ import annotations

import argparse
import tempfile
from decimal import Decimal
from pathlib import Path

import uvicorn

from conftest import build_attention_release_set
from memento.api import create_app
from memento.orchestrator import ingest
from memento.signals import run_signals


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish a temporary synthetic Attention release and serve its API."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="memento-attention-e2e-") as directory:
        fixture_root = Path(directory).resolve()
        manifest_path = build_attention_release_set(fixture_root)
        data_root = fixture_root / "runtime-data"
        canonical_path = ingest(
            manifest_path,
            data_root=data_root,
            classification="synthetic",
        )
        run_signals(
            canonical_path,
            data_root=data_root,
            annual_carrying_cost_rate=Decimal("0.20"),
            carrying_rate_version="synthetic-browser-test-rate-v1",
        )
        uvicorn.run(
            create_app(data_root),
            host=args.host,
            port=args.port,
            log_level="warning",
        )


if __name__ == "__main__":
    main()
