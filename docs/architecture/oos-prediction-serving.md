# Memento Signal Serving Boundary

Status: implemented MVP contract

The calculation job publishes immutable Parquet artifacts; it does not run an HTTP
server. `SignalStore` reads `signal.parquet`, `signal_evidence.parquet`, and the bound
manifest. `PredictionStore` remains available only for historical OOS releases.

## Discovery

`data/signals/current.json` contains only:

```json
{"manifest":"<signal-set-id>/manifest.json","signal_set_id":"<signal-set-id>"}
```

The pointer changes atomically after a complete prediction release has been written.
The reader rejects absolute paths, traversal, identity mismatches, missing files, and
checksum mismatches.

## API-facing operations

- `run()` returns the immutable run manifest, calculation versions, source release-set
  lineage, source package checksums, cutoff, counts, and file inventory.
- `top_signals(signal_type=None)` returns the immutable overall top ten. A type filter
  removes rows but preserves their overall positions.
- `signal(signal_id)` and `evidence(signal_id)` return one signal and its contracted
  type-specific evidence.

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
