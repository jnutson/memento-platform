# Local Ingestion Boundary

The ingestion entry point accepts one explicit absolute manifest path plus a trusted
Memento classification. It resolves and validates every declared relative path without
following symlinks, hashes every immutable input, and independently checks Parquet
schemas, counts, keys, domains, and references with set-based DuckDB queries.

Retailer mappings live only in the Walmart adapter. Canonical output is written below a
unique staging run, validated there, inventoried, and given a manifest last. The whole
candidate directory is then renamed to its deterministic dataset ID. Analytics may
discover only directories below `data/canonical/` containing `manifest.json`.

Published releases are immutable. An identical manifest and version tuple returns the
existing directory. Failures write only safe rule/count summaries to quarantine and
remove staging; source rows never enter logs or exceptions.

DuckDB execution is capped at 2 GB per ingestion connection. Any analytical spill files
are written beneath that run's ignored staging directory and removed with the rest of
the run workspace after success or failure.
