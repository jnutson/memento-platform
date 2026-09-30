# OOS Prediction Serving Boundary

Status: implemented MVP contract

The Memento calculation job publishes immutable Parquet artifacts; it does not run an
HTTP server. The separate UI/API application reads these artifacts through
`memento.serving.PredictionStore`.

## Discovery

`data/predictions/current.json` contains only:

```json
{"manifest":"<prediction-set-id>/manifest.json","prediction_set_id":"<prediction-set-id>"}
```

The pointer changes atomically after a complete prediction release has been written.
The reader rejects absolute paths, traversal, identity mismatches, missing files, and
checksum mismatches.

## API-facing operations

- `run()` returns the immutable run manifest, calculation versions, source release-set
  lineage, source package checksums, cutoff, counts, and file inventory.
- `top_predictions(limit=10)` returns rank positions 1 through 10 in deterministic
  order. The limit cannot exceed 10.
- `evidence(prediction_id)` returns the 28-day low/base/high calculation trace for one
  prediction, ordered by projection date and path.

Dates, UTC timestamps, decimals, and arrays remain typed values at this boundary. The
HTTP application owns their JSON encoding. It must not recompute scores, change ranks,
or infer a probability from confidence or low/base/high sensitivity paths.

## Source release-set layout

The release-set manifest must be located at
`<release-root>/release-sets/<release-id>/manifest.json`. Both package-manifest
references are safe paths relative to the same `<release-root>` and must stay inside
it. Absolute paths and `..` traversal are rejected. This means the synthetic-data
publisher must place or address the Walmart and Miro extension packages beneath one
common release root before integration.
