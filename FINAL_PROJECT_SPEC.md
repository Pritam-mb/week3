# Molt — Final Week 3 Build Specification

## Decision

Molt will be a local-first CSV automation tool for repetitive expense/export cleanup. It treats an open-weight local model as a **compiler**, not as the runtime:

> The model proposes. Tests decide. A human approves. Deterministic execution does the repetition.

The primary demo is a synthetic expense CSV. Molt learns a constrained JSON recipe once, verifies it against independent fixtures, promotes it only after approval, and then processes compatible files with zero additional model calls. Drift fails closed and is quarantined instead of producing an unverified output.

## Source comparison

### `Molt_Full_MVP_Workflow.md`

This is the broad product specification. It defines the safety model, typed recipe DSL, independent verification, drift detection, repair lifecycle, savings ledger, local Ollama runtime, and the long-term API/UI architecture.

### `readme.md` and `workflow.md`

These files are duplicates of the shorter demo workflow. They add the most important Week 3 proof details:

- compile from a demonstrated input/output pair;
- at most three model feedback attempts;
- graduation checks for holdouts, larger data, reordered columns, missing columns, unrelated columns, and empty input;
- checkpoint files after each step and resumable execution;
- honest optional integration boundaries for Gemma/Ollama, Temporal, Sentry, and DevRelay/Entire;
- a benchmark command and a truthful sponsor-claim checklist.

### Final scope decision

The MVP document describes the complete product, while the shorter workflow describes the challenge-ready slice. This build combines them as follows:

| Area | Final Week 3 decision |
|---|---|
| User flow | Compile → verify/graduation → approve → deterministic reuse → drift/quarantine → repair proposal |
| Input | CSV only, synthetic expense data for the public demo |
| Recipe | Versioned, allowlisted JSON operations; no generated code, `eval`, shell, or arbitrary paths |
| Model | Ollama adapter with configurable Gemma/open-weight model; offline fixture mode keeps the demo runnable without Ollama |
| Execution | Standard-library deterministic interpreter, atomic output, preserved source, stable run records |
| Verification | Independent golden/holdout outputs plus invariants and property checks |
| Recovery | Step checkpoints and resume support; no step is silently repeated after a crash |
| Drift | Missing columns, incompatible values, or unmapped categories block and quarantine |
| Repair | Candidate recipe stays inactive until full regression verification and explicit human approval |
| Persistence | SQLite-backed workspace with immutable recipe versions, runs, verification records, repair proposals, audit events, and ledger events |
| UI | Dependency-free local HTML dashboard served by the Python loopback API, plus the CLI |
| API | Standard-library `ThreadingHTTPServer` on `127.0.0.1` with health, automation, recipe, run, repair, and metrics routes |
| Integrations | Gemma/Ollama, Temporal, Sentry, and DevRelay are optional and must only be claimed after real verification |

## Acceptance criteria

1. `python -m molt demo --offline` runs end to end without network access.
2. The demo profiles an example CSV and produces a constrained candidate recipe.
3. The candidate is rejected if it uses an unknown operation, unsafe argument, or undeclared column.
4. Independent golden and held-out expected outputs pass before approval.
5. Graduation checks cover row growth, column reordering, extra-column preservation, empty input, and required-column drift.
6. Approval creates an active immutable recipe version.
7. At least two compatible inputs execute deterministically with `llm_calls=0`.
8. Runs create atomic outputs, checkpoint state, and ledger records with actual counts.
9. A missing-column or unmapped-category input is blocked before output and quarantined with a report.
10. A repair candidate is separate from the active version and cannot be activated without passing verification and explicit approval.
11. A simulated crash can resume from the latest checkpoint without redoing completed steps.
12. The benchmark separates one-time compile/verification calls from steady-state calls avoided.
13. Documentation states exactly which optional partner integrations were run and which remain unverified.

## Implementation status

The full local MVP now includes:

- deterministic CSV runtime and expanded allowlisted operation DSL;
- SQLite persistence under one configured workspace;
- immutable recipe versions and approval gating;
- verification, idempotence, drift, quarantine, and run reports;
- repair proposal/verification/approval lifecycle;
- checkpoint-capable runtime retained for crash/resume flows;
- polling watched-folder orchestration with archive/done/quarantine routing;
- loopback HTTP API and dependency-free browser dashboard;
- derived savings metrics from persisted execution and ledger records;
- unit, service, watcher, and HTTP integration tests.

The optional live integrations remain separate: Ollama/Gemma requires a locally running model, while Temporal, Sentry, Render, and other partner integrations are not claimed until independently run and recorded.

## Deliberate non-goals

The Week 3 build will not claim a hosted deployment, measured energy savings, a production-grade multi-user database, or verified Temporal/Sentry dashboards unless those are actually run. It will not execute model-generated Python or silently repair ambiguous data.

## Checks

```text
python -m unittest discover -s tests -v
python bench.py
python -m molt demo --offline --approve
```

If Ollama and Gemma are installed locally, the optional check is:

```text
python bench.py --model <gemma-tag>
```

The result must record model name, real calls, and any failure; a fixture-mode run must never be presented as proof of live model quality.
