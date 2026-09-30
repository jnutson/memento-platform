# Memento Attention web app

This is the narrow Attention-only product surface for the deterministic OOS MVP. It
contains the ranked queue, interactive Impact/Reaction/Confidence scene, prediction
detail, and evidence-backed planning context. It deliberately excludes recommendations,
editable scenarios, queue mutation, and the supplied Overview, Forecast, Plan, and
Reports panes.

```bash
npm install
npm run dev
```

The default API origin is `http://127.0.0.1:8000`. Set `MEMENTO_API_ORIGIN` before
starting Next.js to use another loopback port. API contracts live in
`lib/attention/schema.ts`; those Zod schemas are the frontend runtime source of truth and
their TypeScript types are inferred directly.

## End-to-end verification

`npm run test:e2e` runs the fast browser workflow against controlled route fixtures.
`npm run test:e2e:fullstack` publishes a temporary synthetic release and launches the
real Python API and Next.js application before driving the same Attention and planning
workflow. The full-stack test requires the repository `.venv` with development
dependencies installed and does not read or write the external Synthetic Data project.
