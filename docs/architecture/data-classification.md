# Data Classification and Handling

Apply the most restrictive class when uncertain.

| Class | Examples | Source control | Model context | Logs | Local development | Production |
|---|---|---|---|---|---|---|
| Public | Published docs, public schemas | Allowed | Allowed | Allowed | Allowed | Allowed |
| Internal | Architecture, non-secret config, aggregate demo metrics | Allowed when useful | Allowed when minimized | Metadata only | Allowed | Access controlled |
| Synthetic | Generated Walmart-like records with no real entity linkage | Small reviewed fixtures only | Small minimized samples | IDs/counts, not full rows | Allowed in ignored data paths | Demo use only |
| Confidential customer | Retailer feeds, sales, inventory, forecasts, prices, orders, mappings | Prohibited | Prohibited by default; only approved, minimized excerpts | Prohibited; log metadata and counts | Only in approved ignored/encrypted locations | Approved tenant-scoped systems only |
| Restricted | Credentials, tokens, private keys, personal data, regulated data | Prohibited | Prohibited | Prohibited | Secret store or approved protected location only | Secret manager and explicitly approved systems |

## Channel rules

### Source control

Commit code, documentation, schemas, safe configuration examples, and small reviewed
synthetic fixtures. Ignore raw extracts, Parquet outputs, DuckDB/database files,
quarantine files, exports, backups, `.env*` secrets, and credentials.

### Model context

Use schemas, summaries, field names, counts, and synthetic examples. Do not paste raw
customer rows, credentials, or personal data into prompts. Approval to process data is
not approval to disclose it to a model provider.

### Logs and errors

Log run IDs, source names, schema versions, timings, counts, and rule identifiers.
Do not log raw rows, payloads, query parameters containing data, secrets, or database
connection strings. Redact unavoidable sensitive values before emission.

### Local development

Default to synthetic data. Store local inputs and generated artifacts only in ignored
directories with restrictive host access. Docker volumes and temporary exports are
data-bearing assets and must be deleted according to the applicable retention rule.

### Production

Real customer data may enter only after production identity, tenant isolation,
encryption, retention/deletion, backup, monitoring, and incident-response boundaries
are documented and approved. Production data must not be copied into development.

## Before using a dataset

Confirm its owner, provenance, classification, permitted purpose, environment,
retention period, and deletion path. Stop when any of these is unknown for non-synthetic data.
