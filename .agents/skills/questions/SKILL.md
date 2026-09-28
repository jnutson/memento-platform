---
name: questions
description: Answer pre-planning questions through read-only inspection. Use only when the user explicitly invokes $questions.
---

# Questions: read-only discovery

Remain read-only for this invocation. Inspect relevant code, tests, documents, Git
history, and external documentation. Distinguish observed behavior from inference.

Do not edit files, create branches, run artifact-producing checks, mutate databases,
copy datasets, or change external state. If an experiment would write, describe the
smallest follow-up check instead.

Answer directly with repository evidence, uncertainties, and a short next step. If
implementation is also requested, hand it to a separate `$planner` or `$builder`
invocation; do not silently change modes.
