# Memento Analytics Demo

This repository contains a local, deterministic ingestion MVP for a Walmart-shaped
synthetic observable release. It validates an explicit immutable manifest and its six
Parquet datasets, maps them to Memento Retail V1, validates the canonical candidate,
then publishes the whole release with one atomic directory rename.

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/memento-ingest /absolute/path/to/observable/manifest.json \
  --classification synthetic --data-root data
```

Only an explicit regular-file manifest is accepted. The source is never modified or
copied. All data-bearing output stays below the ignored `data/` directory. A published
manifest at `data/canonical/<dataset-id>/manifest.json` is the only analytics discovery
point. Logs contain lifecycle metadata and rule identifiers, never source rows.
