# Molt — Next Session Handoff

**Date:** 2026-10-22
**Workspace:** `D:\week3`
**Primary brief read today:** `final.txt`
**Existing technical workflow:** `workflow.txt`, `Molt_Full_MVP_Workflow.md`, `AUDIT_LOG.md`

## User's current priority

The next session should concentrate first on the **TabPFN advisory integration**, then verify the Ollama/Gemma path after Ollama is installed. The user wants the work paused for today and resumed tomorrow.

## Product direction from `final.txt`

Molt remains a generic local-first CSV automation product:

```text
natural-language task
→ local Gemma proposes constrained recipe
→ strict validation
→ deterministic preview and tests
→ human approval
→ compatible reuse with zero model calls
→ drift block/quarantine
→ repair candidate + full regression + human approval
```

Orders and expense CSVs are examples, not hard-coded product types.

The final brief says:

- CSV only for the MVP;
- no arbitrary generated code;
- preserve sources and write atomic outputs;
- use SQLite;
- Gemma/Ollama is the required AI integration;
- TabPFN is optional and advisory;
- Sentry is useful only with redacted, meaningful spans;
- Temporal is not mandatory and should only be used if a real durable workflow need justifies it.

## What is built now

- Deterministic CSV operation engine with allowlisted operations.
- Strict recipe validation and operation-order checks.
- CSV profiling with inferred types, null counts, duplicates, bounded samples, and fingerprints.
- Masked model context utilities.
- SQLite automations, recipe versions, verification runs, execution runs, repair proposals, artifacts, audit events, watched folders, and ledger events.
- Human approval gate and version rollback.
- Drift blocking, quarantine, atomic outputs, duplicate-run protection, and reports.
- Local HTTP API and browser dashboard.
- Clean workspace initialization through `molt init`.
- Environment configuration through `.env.example`/`.env` and process environment overrides.
- `molt doctor` readiness checks.
- Ollama adapter with configurable endpoint/model, schema-constrained JSON response, masked prompt context, response limits, retries, and readiness states.
- TabPFN adapter behind a feature flag with honest unsupported/unavailable states, explicit supervised target requirements, feature safety checks, holdout scoring, redaction, and no row mutation.
- Sentry adapter with redacted allowlisted spans and failure isolation.
- Optional isolated Temporal adapter, but no live Temporal server/worker evidence. It should not be expanded unless tomorrow's review finds a real durable execution requirement.
- Orders fixtures, compatible fixture, drift fixtures, passing repair fixture, and failing repair fixture.

## Actual verification today

```text
python -m unittest discover -s tests -v
34 tests passed

python -m compileall molt tests bench.py
passed

node --check molt/web/app.js
passed

python bench.py
passed in offline fixture mode

python -m molt --state-dir workspace doctor
passed with Ollama warning: endpoint unreachable

python -m molt --state-dir workspace doctor --require-ollama
expected failure because Ollama is not installed/reachable
```

## External setup still needed

The project now has a local `.env` with safe non-secret defaults and a matching `.env.example`. Edit the local `.env` later rather than committing credentials.

### Ollama/Gemma

The user is installing Ollama. Tomorrow:

```text
ollama --version
ollama pull gemma3:4b
ollama list
python -m molt --state-dir workspace doctor --require-ollama
```

Then perform one real compile using a user CSV and record:

- model tag;
- endpoint;
- compile attempts;
- real model calls;
- response/token metadata when Ollama exposes it;
- recipe validation result;
- verification result;
- latency;
- failure details if compilation does not succeed.

Do not call the fixture recipe live Gemma evidence.

### TabPFN

Before enabling real inference, the user must decide/confirm:

- the supported supervised task and target column;
- the anomaly label;
- model-weight/license/access terms;
- local device choice (`auto`, CPU/GPU as appropriate);
- whether the dataset contains safe numeric, non-sensitive features.

Current implementation intentionally does **not** invent unlabeled anomaly detection because the supported classifier interface needs a target. A real TabPFN run should use a small documented labeled fixture, show flagged holdout rows with redaction, and state clearly that the result is advisory.

Suggested configuration after explicit review:

```text
MOLT_TABPFN_ENABLED=true
MOLT_TABPFN_LICENSE_ACCEPTED=true
MOLT_TABPFN_MODEL=default
MOLT_TABPFN_DEVICE=auto
```

### Sentry

Only needed if the user wants a real Sentry sponsor demonstration. Requires explicit consent because telemetry leaves the machine:

```text
SENTRY_DSN=<configured locally, never committed>
```

Then run compile/verify/run/repair and inspect the redacted trace. No real DSN trace has been run yet.

### Temporal

Do not prioritize Temporal tomorrow unless the user specifically decides the durable run requirement is worth the setup. The optional adapter exists, but `temporalio` and a Temporal server are not installed/running, so no live claim is allowed.

## Tomorrow's build order

1. Confirm `final.txt` remains the product brief and keep scope generic CSV, not orders-only.
2. Review and test the TabPFN adapter against a small labeled fixture.
3. If TabPFN is not reproducible or licensing/access is unclear, leave it disabled and document it honestly rather than forcing it into the core flow.
4. Finish the browser anomaly-review UI if the real TabPFN path is ready.
5. Verify Ollama/Gemma live after the user installs Ollama.
6. Run one live compile and one live repair attempt, capturing actual evidence.
7. Update `AUDIT_LOG.md` with live results and only then decide which sponsor categories are genuinely demonstrable.

## Files to start with tomorrow

```text
molt/anomaly.py
tests/test_anomaly.py
molt/application.py
molt/http_api.py
molt/web/app.js
.env.example
AUDIT_LOG.md
final.txt
```

## Do not do tomorrow without a new decision

- Do not add more sponsor integrations for category count.
- Do not claim live TabPFN, Sentry, Temporal, or Gemma evidence without running it.
- Do not send credentials in chat or commit `.env`.
- Do not replace SQLite or the deterministic core with an external service.
- Do not make TabPFN mutate, delete, rewrite, or quarantine rows.

## Live verification update — 2026-10-22

- Ollama `0.40.8` is installed and `gemma3:4b` is available at `http://127.0.0.1:11434`.
- A real Gemma compile returned a structurally valid recipe, but independent golden/held-out verification rejected it; no model recipe was approved.
- A real Gemma repair proposal completed with one model call, one attempt, 992 prompt tokens, and 307 response tokens. Full regression verification rejected it; the active recipe was unchanged.
- The local `.env` now has a Sentry DSN. It is ignored by Git and must not be copied into docs or chat again.
- A real Sentry SDK smoke workflow initialized successfully, completed a deterministic run with zero model calls, and emitted nine redacted spans. Dashboard receipt was not independently inspected.
- Empty process environment variables were fixed so they no longer hide non-empty `.env` values; this has a regression test.
- Full regression suite after these changes: 35 tests passed. Compileall, browser JavaScript syntax check, and offline benchmark passed.

### Next concrete step

The model-backed compile path now retries schema-valid candidates after independent verification failures with bounded redacted feedback; failed candidates remain rejected and inactive. A fresh live compile after this change still returned `RECIPE_SCHEMA_INVALID` within its configured attempts, so no live Gemma candidate is approved. Keep Gemma candidates and repairs inactive unless they pass the full fixture suite. If sponsor evidence is still needed, inspect the Sentry dashboard for the redacted smoke trace without exposing row data. Do not enable TabPFN until the supported labeled task, license/model-weight access, and safe feature columns are explicitly confirmed.
