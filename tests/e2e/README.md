# End-to-end pipeline tests

This directory contains tests that cross the product's real runtime boundaries. The
first scenario builds a minimized synthetic release set, ingests and canonicalizes
it, publishes deterministic predictions, and reads the result through the typed
Attention HTTP API.

These tests deliberately use only temporary synthetic data. They do not read from
or modify `/Users/mininutson/Desktop/Synthetic Data`, and they do not require a
running database or server.

Run the pipeline suite with:

```bash
.venv/bin/pytest tests/e2e
```

or by marker:

```bash
.venv/bin/pytest -m e2e
```

The suite proves the synthetic release-to-API path without requiring a frontend or
external service.
