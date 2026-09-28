# Contributing

This repository favors correctness, simplicity, security, and speed to learning.

## Principles

- Implement the smallest coherent change that satisfies the accepted requirement.
- Organize code around responsibilities and domain boundaries, not pipeline chronology.
- Keep storage formats, retailer-specific mappings, and schema assumptions behind
  narrow interfaces.
- Prefer deterministic transformations and explicit contracts over hidden behavior.
- Do not generalize for hypothetical retailers; extract a shared abstraction only
  when it simplifies a real second use case.
- Never commit secrets, customer data, production data, or sensitive raw extracts.

## Changes

Keep raw ingestion, canonical retail models, validation, and metrics separable. New
behavior should include synthetic fixtures and tests for its contract, boundary cases,
and failure modes. Errors should identify the failing source and rule without exposing
record contents or credentials.

Before considering a change complete:

1. Run the narrowest useful checks while iterating.
2. Run the repository-required checks for the affected area.
3. Inspect the diff for unrelated changes and sensitive data.
4. Confirm generated data, local databases, Parquet files, and secrets remain ignored.
5. Document any check that could not be run.

Reviews prioritize correctness, accepted intent, data safety, reproducibility, and
maintainability. Findings should describe a concrete consequence, not a preference.
