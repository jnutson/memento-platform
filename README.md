# Memento Signal Demo

This repository contains the deterministic Memento Signal path for Miro Toys. It
publishes ten canonical DuckDB-queryable Parquet datasets and one immutable queue of
Availability Risk, Demand Momentum Gap, and Inventory Imbalance Exposure signals.
Signals retain native economics while type-relative impact, reaction time, and
confidence provide a common rank. The legacy OOS artifact remains readable.

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/memento-ingest /absolute/path/to/release-sets/<release-id>/manifest.json \
  --classification synthetic --data-root data

.venv/bin/memento-predict /absolute/path/to/data/canonical/<dataset-id> \
  --data-root data

.venv/bin/memento-signal /absolute/path/to/data/canonical/<dataset-id> \
  --data-root data --annual-carrying-cost-rate <approved-rate> \
  --carrying-rate-version <approved-version>

.venv/bin/memento-evaluate /absolute/path/to/data/predictions/<prediction-set-id> \
  /absolute/path/to/data/canonical/<later-dataset-id> --data-root data
```

Only an explicit regular-file manifest is accepted. The source is never modified or
copied. All data-bearing output stays below the ignored `data/` directory. A published
manifest at `data/canonical/<dataset-id>/manifest.json` is the only analytics discovery
point. Logs contain lifecycle metadata and rule identifiers, never source rows.

Prediction publication creates immutable `oos_prediction.parquet`,
`oos_prediction_evidence.parquet`, and `demand_forecast_vintage.parquet` artifacts.
Only after all three are written does `data/predictions/current.json` move atomically to
the new set. API code can use `memento.serving.PredictionStore` to retrieve the current
run, top-ten queue, and calculation evidence without scanning raw retail facts or
introducing another database.

Signal execution is split into narrow stages: `orchestrator.py` owns source validation
and canonical publication; `availability_signal.py`, `demand_signal.py`, and
`inventory_signal.py` independently produce unranked candidates and evidence;
`signal_ranking.py` assigns type-relative and overall ranks; and
`signal_publication.py` atomically publishes the ranked set. `signals.py` only prepares
cutoff-safe canonical inputs and coordinates those stages. Serving reads published
artifacts and never invokes metric or ranking code.

## Memento Signal interface

The supported local interface is the read-only FastAPI adapter. Python response models
enforce the contract, and serving never recomputes ranks, scores, sensitivity paths, or
recommendations. Start it after publishing prediction and signal sets:

```bash
.venv/bin/memento-serve --data-root data
```

The service binds to `http://127.0.0.1:8000` by default and exposes `/healthz`,
`/v1/attention`, and `/v1/signals` endpoints.

From the repository root, `make verify` runs the complete Python merge gate, including
the synthetic pipeline and HTTP integration tests. GitHub Actions runs the same gate on
every pull request and every push to `main`. Use `make setup` to create the local Python
virtual environment and install its dependencies.

The complete synthetic pipeline can be exercised independently with
`.venv/bin/pytest tests/e2e` (or `.venv/bin/pytest -m e2e`). See
[`tests/e2e/README.md`](tests/e2e/README.md) for the tested runtime boundary.

## Product direction

The focused product milestone publishes three deterministic signals without execution
controls, editable scenarios, probability claims, Monte Carlo simulation, or black-box
models. See:

- [`docs/product/mvp-product-shape.md`](docs/product/mvp-product-shape.md) for the
  end-state MVP requirements, metric contracts, ranking formula, and acceptance tests.
- [`docs/product/mvp-metric-contract.md`](docs/product/mvp-metric-contract.md) for the
  exact formulas, forecast/projection mechanics, thresholds, and no-drift rules.
- [`docs/plans/insights-mvp-data-scope.md`](docs/plans/insights-mvp-data-scope.md) for
  the bounded observable-data scope and ownership boundaries.
- [`docs/product/memento-glossary.md`](docs/product/memento-glossary.md) for Walmart-
  aligned source and Memento-derived terminology.
