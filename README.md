# Memento Analytics Demo

This repository contains the local deterministic data path for the focused Miro Toys
out-of-stock prediction MVP. It accepts an atomic Walmart-plus-Miro release set,
publishes nine canonical DuckDB-queryable Parquet datasets, and produces an immutable
daily queue ranked by lost-sales impact, reaction time, and confidence. The historical
standalone six-dataset Walmart adapter remains supported.

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/memento-ingest /absolute/path/to/release-sets/<release-id>/manifest.json \
  --classification synthetic --data-root data

.venv/bin/memento-predict /absolute/path/to/data/canonical/<dataset-id> \
  --data-root data

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

## Attention interface

The `web/` application is the single-pane interactive Attention workflow. It consumes
the immutable queue through a local FastAPI adapter; Python response models enforce the
server contract and frontend Zod schemas validate every JSON payload before it reaches
React.

Run the API and frontend in separate terminals after publishing a prediction set:

```bash
.venv/bin/memento-serve --data-root data

cd web
npm install
npm run dev
```

Open `http://127.0.0.1:3000/attention`. Next.js proxies same-origin `/api/attention`
requests to the loopback service at `http://127.0.0.1:8000`; override the service origin
with `MEMENTO_API_ORIGIN` when needed. The API is read-only and does not recompute ranks,
scores, sensitivity paths, or recommendations.

Frontend verification commands are `npm run typecheck`, `npm run lint`, `npm test`,
`npm run build`, and `npm run test:e2e`. The Playwright workflow uses minimized route
fixtures; Python integration tests cover the live Parquet-to-HTTP boundary.

The complete synthetic pipeline can be exercised independently with
`.venv/bin/pytest tests/e2e` (or `.venv/bin/pytest -m e2e`). From `web/`, run
`npm run test:e2e:fullstack` to verify the browser, real API, and published Parquet
artifacts together. See
[`tests/e2e/README.md`](tests/e2e/README.md) for the boundary between these pipeline
tests and the browser workflow tests in `web/tests/e2e`.

## Product direction

The focused product milestone has one capability: predict when a scoped Walmart
store-item will go out of stock and rank eligible predictions by estimated lost retail
sales, remaining reaction time, and prediction confidence for **Miro Toys**. Interactive
scenario planning and secondary insights are deferred. The initial model uses only
interpretable deterministic equations and low/base/high WAPE sensitivity paths—no
Monte Carlo simulation or black-box model. See:

- [`docs/product/mvp-product-shape.md`](docs/product/mvp-product-shape.md) for the
  end-state MVP requirements, metric contracts, ranking formula, and acceptance tests.
- [`docs/product/mvp-metric-contract.md`](docs/product/mvp-metric-contract.md) for the
  exact formulas, forecast/projection mechanics, thresholds, and no-drift rules.
- [`docs/plans/insights-mvp-data-scope.md`](docs/plans/insights-mvp-data-scope.md) for
  the bounded observable-data scope and ownership boundaries.
- [`docs/product/memento-glossary.md`](docs/product/memento-glossary.md) for Walmart-
  aligned source and Memento-derived terminology.
- [`docs/plans/attention-ui-integration.md`](docs/plans/attention-ui-integration.md) for
  the accepted Attention UI integration scope and verification criteria.
