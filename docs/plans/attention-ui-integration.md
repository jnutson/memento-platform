# Attention UI Integration Plan

Status: proposed implementation direction
Scope: local synthetic-data MVP demo
Authority: the implemented prediction and serving contracts remain authoritative

## Goal

Build the narrowest deep product surface that demonstrates the existing Memento OOS
prediction capability through the supplied Attention UI without changing, obscuring, or
recomputing the engine's outputs.

The finished demo will contain one product pane: **Attention**. It will preserve the
useful interactivity of the supplied UI—3D exploration, selection, keyboard navigation,
detail inspection, synchronized chart/table hover, and a planning-context drill-down—
while presenting the immutable top-ten store-item queue and its calculation evidence.

The integration should meet the UI in the middle:

- Build presentation and serving capabilities that are missing today.
- Adapt UI terminology and layout where the existing engine has a stronger contract.
- Do not change engine formulas or outputs merely to match synthetic UI assumptions.
- Do not present recommendations, execution controls, probabilities, or editable
  scenarios that the MVP cannot support truthfully.

## Product outcome

The user can open Attention and:

1. See the current immutable prediction run and its ranked top-ten store-item queue.
2. Explore impact, reaction, and prediction-confidence scores in an interactive 3D view.
3. Select a prediction from either the scene or ranked list without changing its rank.
4. Understand the predicted OOS date, sensitivity range, estimated exposure, response
   window, confidence components, and scheduled inbound.
5. Drill into the deterministic 28-day low/base/high projection and calculation trace.
6. Verify the run cutoff, source lineage, and calculation versions.

This is an interactive evidence explorer. It is not an order-management, replenishment,
scenario-planning, or recommendation product.

## Authoritative boundaries

The following existing behavior is preserved:

- Prediction grain is `prediction_as_of x store_id x product_id x predicted episode`.
- The UI displays at most ten predictions in engine-provided `rank_position` order.
- Ranking uses only published `impact_score`, `reaction_score`, and
  `prediction_confidence_score` values.
- The frontend never recomputes scores, rank, eligibility, or tie-breaks.
- Low/base/high paths are fixed deterministic sensitivity paths, not probabilities or
  user-editable scenarios.
- Confidence is an interpretable score, not an OOS probability.
- Published predictions and evidence remain immutable and source-lineage preserving.
- The existing DuckDB-over-Parquet analytical boundary remains unchanged.
- No additional persistent datastore is introduced.

## Included UI slice

Import only the frontend pieces needed for:

- the application shell with a single Attention navigation item;
- the Attention summary strip;
- the 3D score scene;
- the ranked prediction list;
- the selected-prediction detail/planning-context pane;
- the evidence chart and calculation table; and
- shared styling and responsive measurement utilities required by those components.

Do not import the Overview, Forecast, standalone Plan, or Reports panes. Do not import
their API routes, stores, data generators, charts, contracts, or placeholder downloads.

## UI semantics

### Summary strip

Display:

- eligible candidate count from the immutable run manifest;
- displayed prediction count;
- total estimated lost units across the displayed queue; and
- total estimated lost sales across the displayed queue.

Totals must be labeled as estimates over the 28-day prediction horizon. They must not be
described as units short within lead time, realized loss, or POS sales.

### 3D score scene

Map published scores directly to the three axes:

```text
x = prediction_confidence_score
y = impact_score
z = reaction_score
```

Convert `[0,1]` to scene coordinates only for rendering. Preserve the original numeric
values for labels and accessibility text.

Retain rotation, zoom, hover, selection, focus, reset, and keyboard navigation. Remove
the supplied UI's `Important` box and threshold filter. No replacement importance
threshold or top-three classification is introduced.

### Ranked list

Each row displays:

- immutable `rank_position`;
- Miro item name and safe display identifier;
- store name and safe display identifier;
- base predicted OOS date;
- estimated lost units; and
- published rank score.

Selection or filtering must not renumber rows. The client must not sort independently of
the API response.

### Detail and planning-context pane

Display existing prediction outputs:

- base, earliest, and latest OOS dates;
- estimated lost units and estimated lost sales;
- impact, reaction, confidence, and composite rank scores;
- days until predicted OOS;
- minimum reaction days and action slack;
- forecast WAPE and forecast quality;
- data completeness;
- timing-stability score and OOS-date span;
- starting projected on hand from base-path day one; and
- every dated scheduled-inbound quantity within the horizon.

Use **Reaction**, not **Urgency**, for the score axis and meter. Use **minimum reaction
days**, not **lead time**. Use **scheduled inbound**, not **in transit**, unless a future
output specifically exposes Walmart Store In Transit under its contracted definition.

Do not show weeks of supply or constant weekly velocity. Neither is a published MVP
metric, and deriving them in the client would introduce new business logic.

### Evidence drill-down

Replace the supplied fabricated six-week history and constant-velocity projection with
the published 28-day evidence trace.

The visualization shows:

- projected ending on hand for low, base, and high demand paths;
- fixed-path visibility toggles;
- base-path daily demand;
- scheduled inbound by date;
- base-path lost units after depletion;
- the base predicted OOS date; and
- earliest/latest sensitivity dates when present.

Chart and table hover remain synchronized. Path toggles only change visibility; they do
not modify assumptions or recompute a scenario. Daily dates remain the primary grain so
the UI does not hide exact depletion timing behind weekly aggregation.

### Deterministic explanation

Generate factual copy only from published prediction and evidence fields. The explanation
may state:

- when the base path depletes;
- the low/high sensitivity range;
- what inbound is scheduled before or after depletion;
- the estimated 28-day exposure;
- whether action slack is positive or negative; and
- which confidence component most constrains the score.

Do not recommend expediting, transferring, ordering, allocating, or changing a PO. Do
not imply DC inventory or execution feasibility.

## Controls explicitly removed

Remove or omit:

- `Important` classification, count, box, and filter;
- `Expedite PO`;
- `Transfer from DC`;
- `Dismiss` and client-side queue removal;
- editable forecast, demand, inbound, or timing assumptions;
- calculated WOS and constant velocity;
- single-receipt assumptions;
- percentage/probability presentation of confidence; and
- any client-side ranking or metric formula.

## Serving design

Retain `memento.serving.PredictionStore` as the trusted read boundary over immutable
prediction artifacts. Add the smallest local, read-only HTTP adapter needed by the web
application.

Use FastAPI with Pydantic response models and Uvicorn as the local server. The service
binds to `127.0.0.1` by default. The Next.js application exposes same-origin
`/api/attention/...` requests through a development rewrite to the loopback Python API;
the browser does not call a second origin and the Python service does not enable a broad
CORS policy.

Proposed endpoints:

```text
GET /healthz
GET /v1/attention
GET /v1/attention/{prediction_id}
```

`GET /v1/attention` returns:

- safe run metadata;
- candidate and display counts;
- calculation versions and cutoff;
- displayed-queue totals; and
- top-ten prediction summaries in existing rank order.

`GET /v1/attention/{prediction_id}` returns:

- the selected published prediction;
- resolved item and store display identity;
- its complete 84-row evidence trace;
- a deduplicated scheduled-inbound display schedule; and
- safe lineage/version metadata.

Bind the local API to loopback by default. Do not expose filesystem paths, source rows,
raw payloads, credentials, or private evaluator truth.

Initialize the adapter with the repository data root. Resolve predictions from
`<data-root>/predictions` and the bound canonical release only from
`<data-root>/canonical/{canonical_dataset_id}`. Resolve both paths strictly beneath the
configured root before reading them.

### Display identity resolution

Prediction output currently carries stable `product_id` and `store_id` values. Resolve
display names in the serving/view-model layer from the exact canonical dataset named by
the prediction manifest's `canonical_dataset_id`:

- `company_item` supplies the Miro item name and company item identifier;
- `product` supplies safe retailer item attributes when required; and
- `location` supplies the store display name and safe source location identifier.

Validate the canonical manifest and declared files before reading those dimension
tables. Do not denormalize presentation fields into an already-published prediction set
or scan raw source extracts.

### JSON encoding

Define an explicit API schema. Encode dates and UTC timestamps as ISO-8601 strings and
decimal values as fixed-point JSON strings without binary floating-point drift. Preserve
null sensitivity dates.
Return scores with their contracted `[0,1]` meaning; convert to a 0–100 display scale only
in formatting code.

Every success payload includes `api_contract_version`. Every error uses one versioned,
non-sensitive envelope containing `api_contract_version`, a stable error `code`, and a
safe human-readable `message`. Dates use `YYYY-MM-DD`; timestamps use UTC ISO-8601 with
an explicit offset. Frontend presentation adapters may convert validated decimal strings
to JavaScript numbers only where rendering libraries require them; those numbers must
never feed business calculations.

### Type enforcement across the API boundary

Enforce the contract on both sides of the JSON boundary rather than relying on
TypeScript compile-time checking alone:

- Define the Python HTTP responses with typed validation models at the existing serving
  boundary (for example, Pydantic models).
- Define runtime response schemas in frontend `.ts` modules using Zod or an equivalent
  schema validator.
- Infer the frontend domain types from those runtime schemas so validation and static
  types cannot drift independently.
- Parse every API response before it enters application state or a React component.
- Keep transport, schema, parsing, and formatting logic in `.ts` files; reserve `.tsx`
  for components that render already-validated domain values.
- Reject malformed or contract-incompatible responses with an explicit integrity error;
  do not coerce missing, invalid, or out-of-range business fields into plausible values.

The initial implementation may maintain corresponding Python and TypeScript schemas
manually because the API is deliberately small. Add schema-code generation only if
contract drift becomes a demonstrated maintenance problem. Moving the API itself to
TypeScript is not required and would unnecessarily bypass or duplicate the existing
Python `PredictionStore` boundary.

## Implementation sequence

### Phase 1 — Harden and selectively import the frontend

- Create a `web/` application inside this repository.
- Copy only the Attention slice and required shell/shared utilities.
- Upgrade vulnerable frontend dependencies before committing them.
- Generate and commit the package-manager lockfile.
- Remove synthetic Attention data and all unused pane dependencies.
- Keep the Python and frontend dependency boundaries separate and explicit.
- Add the minimum verification toolchain: TypeScript `--noEmit`, ESLint, Vitest, React
  Testing Library, and Playwright.

### Phase 2 — Build the read-only API view model

- Extend the serving layer to resolve the current prediction and canonical releases.
- Add safe item/store display identity resolution.
- Define typed Python queue and detail response models with boundary validation.
- Aggregate displayed-queue totals without changing candidate rows.
- Transform evidence into a display schedule without changing projection values.
- Add deterministic JSON encoding and error responses.

### Phase 3 — Connect the Attention queue

- Replace `lib/attention/data.ts` synthetic generation with typed API data.
- Add `.ts` runtime schemas and infer the frontend types from them.
- Validate every response before storing or rendering it.
- Render engine-provided summary values, scores, ranks, and identities.
- Adapt the 3D scene to Impact, Reaction, and Confidence.
- Preserve selection, hover, keyboard navigation, rotation, zoom, and reset.
- Implement loading, integrity-error, zero-candidate, and fewer-than-ten states.
- Keep the zero-candidate copy neutral: `No eligible predictions in this run.` Do not
  imply suppression reasons that the engine has not published.

### Phase 4 — Connect the planning-context drill-down

- Render sensitivity dates, reaction timing, confidence components, and inbound schedule.
- Replace weekly fabricated data with the daily evidence chart and table.
- Add fixed-path visibility toggles and synchronized hover.
- Add deterministic explanation copy and a compact lineage/version disclosure.
- Verify that no control implies mutation, execution, feedback, or scenario recomputation.

### Phase 5 — Verification and import cleanup

- Verify Python serving behavior with synthetic fixtures.
- Verify frontend type checking, linting, tests, and production build.
- Exercise the complete Attention workflow with Playwright in a real browser.
- Run a dependency audit and resolve high or critical findings.
- Inspect the final diff for generated data, secrets, raw payloads, or unrelated changes.

## Required verification

### Serving tests

- Current-pointer, manifest, checksum, and path validation remain enforced.
- Queue order exactly matches `rank_position` from the published artifact.
- Limits remain between 1 and 10.
- Item and store identities resolve only from the bound canonical dataset.
- Dates, decimals, nulls, and arrays serialize deterministically.
- Detail requests cannot escape the current immutable release.
- Multiple inbound dates remain distinct and are not double-counted across paths.
- Empty queues and corrupt/missing releases return distinguishable safe errors.

### Engine-facing integration tests

- A multi-candidate fixture exercises ordering and deterministic tie-breaks.
- At least one fixture has negative action slack.
- At least one fixture has multiple dated inbound quantities.
- At least one low-demand path does not deplete within the horizon.
- Confidence components vary independently across fixture predictions.
- Replaying identical inputs produces identical response content and ordering.

### Frontend tests

- Valid queue and detail payloads pass runtime schema validation.
- Missing, malformed, and out-of-range fields fail before reaching React components.
- Runtime schemas and inferred TypeScript types remain the single frontend contract.
- The UI never invokes ranking or score formulas.
- Rows retain immutable rank positions after selection and filtering interactions.
- The scene and list select the same prediction.
- Keyboard navigation never changes ordering.
- Confidence is labeled as a score, never as probability.
- Reaction, scheduled inbound, estimated lost units, and sensitivity paths use contracted
  terminology.
- The evidence table and chart show the same daily values.
- Fixed-path toggles affect visibility only.
- No recommendation, dismissal, mutation, or scenario-editing control is present.

### Browser acceptance flow

1. Open Attention and see the current run and ranked queue.
2. Select a prediction from the list and from the 3D scene.
3. Move through predictions using buttons and arrow keys without rank changes.
4. Open the planning-context drill-down.
5. Inspect the base OOS date and low/high sensitivity bounds.
6. Hover the daily chart and observe the matching evidence-table row.
7. Toggle fixed paths without changing any displayed calculation.
8. Inspect scheduled inbound, response window, confidence components, and lineage.
9. Return to the queue with the same ordering and selection semantics.

## Acceptance criteria

The implementation is complete when:

1. Only the Attention product pane is present.
2. Every displayed business value originates from the current immutable prediction,
   evidence, run manifest, or its bound canonical dimension data.
3. The displayed queue is the engine's exact top ten, at store-item grain and in its
   original order.
4. The 3D scene uses Impact, Reaction, and Confidence without client-side scoring.
5. The detail pane exposes the base date, sensitivity range, estimated exposure,
   reaction window, confidence components, and all scheduled inbound.
6. The drill-down faithfully renders the 28-day low/base/high evidence trace.
7. Confidence is never presented as a probability, and sensitivity paths are never
   presented as scenarios or prediction intervals.
8. No action recommendation, order mutation, allocation, DC-feasibility claim,
   dismissal, or feedback behavior is present.
9. No existing prediction, ingestion, canonicalization, validation, lineage, or storage
   contract is weakened to accommodate the UI.
10. Python response models and frontend `.ts` runtime schemas enforce the API contract,
    and React components receive only validated, statically typed domain values.
11. Relevant Python and frontend checks pass, the browser workflow is verified, and the
    diff contains only intended source, tests, documentation, and safe dependency files.

## Known follow-up decision

The metric contract requires reason codes for suppressed candidates, while the current
prediction implementation skips several ineligible cases without publishing safe
aggregate diagnostics. This does not block a nonempty Attention queue. Before promising
an explanatory zero-risk state, decide whether to add aggregate suppression counts as a
versioned engine output. Do not infer or fabricate those explanations in the frontend.

## Non-goals

- Overview, Forecast, standalone Plan, or Reports panes.
- Historical trend or six-week actuals visualization.
- Editable what-if assumptions or scenario persistence.
- Recommended actions or execution workflows.
- Human feedback, dismissal persistence, or ranker learning.
- DC inventory, transfer feasibility, order quantities, or supply-network modeling.
- Multiple retailers, companies, brands, or unrestricted cohorts.
- Production deployment, authentication, tenancy, or access-control design.
