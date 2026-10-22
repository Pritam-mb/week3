# Molt Full MVP Audit Log

**Project:** Molt
**Workspace:** `D:\week3`
**Primary source of truth:** `workflow.md`
**Supporting source:** `Molt_Full_MVP_Workflow.md`, `FINAL_PROJECT_SPEC.md`
**Last audit update:** 2026-10-22

## Product being built

Molt is a single-user, local-first CSV automation application.

The product rule is:

> The open-weight model proposes a constrained recipe. Molt validates and tests it. A human approves it. Deterministic code performs compatible future runs.

Molt is not a general-purpose agent. It does not execute model-generated Python, shell, SQL, JavaScript, browser commands, or unrestricted filesystem actions.

## Explicit decisions

### One project

This workspace contains one project only:

```text
D:\week3\
```

Temporary `.molt-demo*` directories created during earlier testing were removed. Runtime state is now kept in one selected workspace directory:

```text
workspace/
├── molt.sqlite3
├── in/
├── done/
├── quarantine/
├── reports/
├── archive/
├── checkpoints/
└── uploads/
```

### Temporal is optional, not required

Temporal is now included as an isolated optional durable-execution integration because it is useful for retrying/resuming long-running approved runs. The core Molt application remains usable without a Temporal server or the `temporalio` package. Drift is returned as data and is not blindly retried.

The watched-folder workflow uses a local polling thread, as allowed by the MVP requirements.

### Optional integrations

- **Gemma/Ollama:** core compile and repair integration. Live model verification depends on Ollama and a locally installed Gemma model.
- **TabPFN:** optional advisory anomaly analysis. It never deletes, rewrites, or quarantines rows by itself.
- **Sentry:** optional redacted telemetry. The application works with telemetry disabled, and telemetry failure must never break data processing.
- **Temporal:** optional durable execution for approved runs; no live server/worker run has been verified in this workspace yet.

No integration is described as demonstrated until it has a real local run and recorded evidence.

## Operational readiness update

The environment/sanity gap identified during the latest audit is now addressed:

- `.env.example` defines workspace, server, limits, Ollama endpoint/model, timeouts, retries, local-only mode, and optional integrations.
- `.env` is loaded without a third-party dependency; process environment variables override it.
- `python -m molt doctor` reports Python, workspace/SQLite, Ollama server/model readiness, telemetry, and optional TabPFN status.
- `python -m molt init` creates a clean empty workspace without a pre-approved demo automation.
- `MoltService.health()` checks Ollama `/api/tags` and distinguishes `ready`, `model_missing`, and `unreachable`.
- Ollama requests use a canonical schema, masked profile context, configurable timeout/retry/response limits, and active-recipe/drift context for repair.
- Server startup reports `SERVER_ALREADY_RUNNING` or `SERVER_BIND_FAILED` instead of silently failing.
- Ollama is now reachable at `http://127.0.0.1:11434` with `gemma3:4b` installed; live compile and repair attempts are recorded below.

## Requirements from `workflow.md`

### Core workflow

- [x] Local CSV profile with row/column counts, headers, inferred types, null counts, duplicates, samples, and fingerprints.
- [x] Constrained JSON recipe validation.
- [x] Allowlisted deterministic operation registry.
- [x] Preview/execution on a working copy.
- [x] Golden and held-out verification fixtures.
- [x] Structural checks, idempotence where applicable, column-order checks, empty-input check, and extra-column check.
- [x] Explicit recipe approval gate.
- [x] Immutable SQLite recipe versions.
- [x] Deterministic compatible execution with zero runtime model calls.
- [x] Drift blocking for missing columns, unknown mapping values, malformed values, and invariant failures.
- [x] Quarantine and per-run report generation.
- [x] Repair candidate separated from active recipe.
- [x] Full regression verification before repair approval.
- [x] Previous recipe versions retained for audit and recovery.
- [~] Browser upload, profiling, compile selection, preview, verification, and approval path is wired; structured recipe editing and fixture-management screens remain to be finished.
- [x] Live Gemma/Ollama compile evidence on this machine; a real candidate was generated and then rejected by independent verification.
- [x] Live Sentry SDK trace path; a real DSN initialized the SDK and a smoke workflow emitted nine redacted spans. Dashboard receipt was not independently inspected.
- [ ] TabPFN anomaly evidence on an eligible dataset; the supervised advisory adapter and tests pass, but no real model-weight inference was run.
- [ ] Live Temporal server/worker workflow evidence; the optional adapter and no-SDK behavior tests pass, but no Temporal server was available.

### Safety

- [x] No generated code execution.
- [x] No unrestricted shell or filesystem operations.
- [x] Workspace-root path validation.
- [x] Symlink rejection.
- [x] Input preservation by default.
- [x] Atomic output writing.
- [x] Output overwrite rejection.
- [x] File and row limits.
- [x] Stable error codes for core failures.
- [x] Masked model context helper.
- [x] Formula-injection warnings are recorded for output values beginning with spreadsheet formula characters; explicit sanitization choice remains.
- [x] Execution timeout is checked before output publication; hard interruption of a running Python operation remains future hardening.

### Persistence

- [x] SQLite database initializer.
- [x] Automation records.
- [x] Recipe version records.
- [x] Artifact records.
- [x] Verification records.
- [x] Execution run records.
- [x] Repair proposal records.
- [x] Watched-folder records.
- [x] Ledger events.
- [x] Audit events.
- [ ] Complete verification-check child records for every individual check.
- [ ] Migration/import command for old JSON state, if old state is found.

### API

- [x] `GET /api/health`
- [x] `GET /api/metrics`
- [x] `GET /api/metrics/ledger`
- [x] `POST /api/files/profile` multipart CSV upload
- [x] `POST /api/automations`
- [x] `GET /api/automations`
- [x] `GET /api/automations/{id}`
- [x] `POST /api/automations/{id}/profile`
- [x] `POST /api/automations/{id}/compile`
- [x] `POST /api/automations/{id}/generate-recipe`
- [x] `POST /api/automations/{id}/validate`
- [x] `POST /api/automations/{id}/preview`
- [x] `POST /api/automations/{id}/tests`
- [x] `POST /api/automations/{id}/approve`
- [x] `POST /api/automations/{id}/runs`
- [x] `GET /api/automations/{id}/runs`
- [x] `GET /api/runs/{run_id}`
- [x] `POST /api/runs/{run_id}/repair`
- [x] `POST /api/recipes/{version_id}/approve`
- [x] `POST /api/recipes/{version_id}/reject`
- [x] `POST /api/automations/{id}/anomaly-analysis`
- [x] `POST /api/repair-proposals/{id}/verify`
- [x] `POST /api/repair-proposals/{id}/approve`
- [x] `POST /api/repair-proposals/{id}/reject`
- [x] Watched-folder configuration endpoint
- [ ] Consistent response naming aligned with every example in the workflow document.
- [ ] Dedicated route for downloading approved output/report artifacts.

### Dashboard

- [x] Local static dashboard served by the API.
- [x] Overview metrics.
- [x] Automation list/details.
- [x] Recipe review evidence.
- [x] Run history.
- [x] Drift/repair section.
- [x] Empty/loading/error states.
- [x] Browser upload control wired to `/api/files/profile`.
- [~] Browser profile/compile/preview actions are wired; the compile action supports fixture mode or a prompted local Ollama model.
- [ ] Browser structured recipe editing controls.
- [ ] Browser fixture/expected-output management.
- [ ] Browser anomaly review panel.
- [ ] Browser telemetry status and trace link.

### Benchmark

- [x] Deterministic reuse timing and actual call-count output.
- [x] Explicit calls-avoided calculation.
- [x] Claim boundary separating inference avoidance from energy savings.
- [ ] Repeated-LLM baseline implementation.
- [ ] Fixed-script baseline implementation.
- [x] Orders benchmark dataset, compatible input, drift inputs, and passing/failing repair recipes are included.
- [ ] Published raw benchmark summary with environment details.

## Current source structure

```text
molt/
├── core.py              # recipe validation, CSV runtime, verification
├── application.py       # SQLite-backed application services
├── db.py                # schema and database connections
├── config.py            # one workspace and operational limits
├── state_machine.py     # legal lifecycle transitions
├── ollama.py            # local Ollama adapter
├── privacy.py           # redacted model context helpers
├── telemetry.py         # optional redacted Sentry boundary
├── anomaly.py           # optional TabPFN boundary
├── watcher.py           # stable-file polling and routing
├── http_api.py          # loopback API and dashboard server
├── cli.py               # command-line adapter
└── web/
    ├── index.html
    ├── app.js
    └── style.css
```

## Build sequence from this point

### Phase 1 — Finish the core workflow

1. Complete the remaining browser structured-editing and fixture-management path.
2. Add structured user fixture storage and display.
3. Add output preview diffs and invariant evidence.
4. Align API response fields with the documented run examples.

### Phase 2 — Finish repair and recovery evidence

1. Add an end-to-end repair test using the orders fixtures.
2. Demonstrate a deliberately bad repair that fails a historical fixture.
3. Demonstrate a passing repair waiting for approval.
4. Approve the repair and rerun the triggering file.
5. Add explicit rollback to a previous version.

### Phase 3 — Finish safety and privacy

1. Enforce execution timeout.
2. Add formula-injection warning/sanitization choice.
3. Add stronger preflight drift reports with redacted examples.
4. Ensure no raw values enter logs or telemetry.
5. Add tests for path traversal, symlinks, malformed rows, upload limits, and overwrite rejection.

### Phase 4 — Finish benchmark evidence

1. Use the orders dataset as the canonical benchmark.
2. Add a repeated-model baseline interface that records actual calls when Ollama is available.
3. Add a fixed-script baseline with clearly stated scope.
4. Record compile calls, repair calls, deterministic calls, latencies, checks, and blocked drift cases.
5. Report estimates separately from measurements.

### Phase 5 — Optional integrations

1. Run Gemma through Ollama locally and preserve the actual result, including failure if it cannot compile within three attempts.
2. If TabPFN is installed and licensing/task conditions are satisfied, run the advisory analyzer and record its exact model/configuration.
3. If `SENTRY_DSN` is explicitly configured, run the redacted tracing path and record spans. Without it, keep local-only mode.
4. Keep Temporal optional and isolated; do not make the core workflow depend on it.

## Verification commands

Run from `D:\week3`:

```text
python -m compileall molt tests bench.py
python -m unittest discover -s tests -v
node --check molt/web/app.js
python bench.py
python -m molt --state-dir workspace init-demo --approve
python -m molt --state-dir workspace serve
```

Dashboard smoke check:

```text
GET http://127.0.0.1:8765/api/health
GET http://127.0.0.1:8765/api/metrics
GET http://127.0.0.1:8765/
```

## Evidence policy

Only these statements may be marked complete after a command or test actually proves them. A fixture-mode recipe is not live Gemma evidence. A configured Sentry adapter is not a Sentry trace. A detected TabPFN package is not a completed anomaly demonstration. Calls avoided are an inference metric, not measured electricity savings.

## Definition of done

Molt is final when a new user can complete this sequence through the local app:

```text
upload orders CSV
→ describe transformation
→ profile and review masked context
→ compile or edit a constrained recipe
→ preview output
→ run full verification
→ approve recipe
→ run a compatible CSV with model_calls = 0
→ block an unknown-status CSV
→ inspect redacted drift report
→ request repair
→ reject a regression repair
→ verify and approve a passing repair
→ rerun the triggering CSV
→ inspect history, rollback option, traces/telemetry status, and ledger
```

The application must work without TabPFN, Sentry, or a live Ollama connection for already-approved deterministic runs. It must never claim those optional integrations were demonstrated unless their actual evidence is present.

## Session closeout — 2026-10-22

The final product brief was re-read from `final.txt`. A resumable plan for tomorrow is saved in `NEXT_SESSION_HANDOFF.md`. The next priority is TabPFN verification first, followed by live Ollama/Gemma verification after the user's Ollama installation.

### Work completed today

- Re-read the updated workflow specification and used it as the implementation reference.
- Added environment configuration through `.env.example` and optional local `.env` loading.
- Added `molt init` for a clean empty workspace.
- Added `molt doctor` for runtime, workspace, SQLite, Ollama, telemetry, and TabPFN readiness.
- Added canonical Ollama configuration: endpoint, model, timeout, retry count, response-size limit, and JSON recipe schema.
- Added Ollama readiness states: `ready`, `model_missing`, and `unreachable`.
- Added masked model context and repair prompts containing the active recipe and drift report.
- Added clear server errors for an already-running port and bind failures.
- Added optional TabPFN supervised advisory triage with explicit target/label requirements, license acknowledgment, sensitive-feature exclusion, holdout scoring, redaction, and no row mutation.
- Added optional redacted Sentry span handling with failure isolation.
- Added optional Temporal durable execution around the existing Molt service, checkpoints, idempotency, and non-retryable drift outcomes.
- Added orders fixtures and good/bad repair fixtures.
- Added Ollama, TabPFN, Sentry, Temporal, HTTP, watcher, application, and core tests.

### Actual checks completed today

```text
python -m unittest discover -s tests -v
Ran 34 tests
OK

python -m compileall molt tests bench.py
PASS

node --check molt/web/app.js
PASS

python bench.py
PASS — offline fixture benchmark; 2 deterministic calls avoided

python -m molt --state-dir workspace doctor
PASS for Python/workspace/SQLite; WARN for Ollama because it is unreachable

python -m molt --state-dir workspace doctor --require-ollama
EXPECTED FAIL — Ollama is not installed or reachable on this machine

python -m molt --state-dir workspace serve
PASS — server starts and reports SERVER_ALREADY_RUNNING when a second instance is attempted

HTTP smoke check
PASS — /api/health, /api/config, and / return successfully

python -m molt --state-dir workspace temporal worker
EXPECTED FAIL — TEMPORAL_UNAVAILABLE because the optional SDK/server is not installed/running
```

### Current sponsor readiness

| Integration | Code/tests | Live external evidence | Current status |
|---|---:|---:|---|
| Gemma through Ollama | Yes | Yes | Live compile and repair calls ran; verification rejected the generated candidates |
| TabPFN | Yes, optional advisory supervised path | No | Requires explicit license/access setup and real model-weight inference |
| Sentry Agent Tracing | Yes, redacted and non-blocking | Yes | Real DSN initialized the SDK; nine redacted smoke-workflow spans emitted; dashboard receipt not inspected |
| Temporal | Yes, optional durable boundary | No | Requires `temporalio`, a Temporal server, and a worker |

### What is needed from the user

Nothing is required to continue the offline/local deterministic project. The current code and tests are usable without external credentials.

Only provide the following if live sponsor demonstrations are wanted in a future session:

1. **Ollama/Gemma:** install/start Ollama and pull the selected model, currently `gemma3:4b`:
   ```text
   ollama pull gemma3:4b
   ```
2. **Sentry:** provide a Sentry DSN only if you explicitly consent to telemetry leaving the machine. A real trace must then be run and reviewed.
3. **TabPFN:** confirm the intended supported task and license/model-weight access before enabling `MOLT_TABPFN_ENABLED=true` and `MOLT_TABPFN_LICENSE_ACCEPTED=true`.
4. **Temporal:** install the optional extra and provide a reachable Temporal server, normally `127.0.0.1:7233`:
   ```text
   pip install -e ".[temporal]"
   ```

Do not send credentials in chat or commit them to the repository. Configure them locally in `.env` or the relevant local service.

### Session status

The project is saved in the single workspace `D:\week3`. The local server is running at `http://127.0.0.1:8765/`. The deterministic core is tested. Live Gemma and Sentry SDK paths now have bounded local evidence; TabPFN and Temporal remain unverified.

## Live integration update — 2026-10-22

### Ollama/Gemma

Readiness and model installation:

```text
ollama version 0.40.8
gemma3:4b installed
python -m molt --state-dir workspace doctor --require-ollama
PASS — server and configured model ready
```

A real compile against `workspace/in/expense-demo.csv` returned a validated recipe from `gemma3:4b`. The first candidate failed Molt's independent golden/held-out verification and was not approved. A real repair proposal also completed with one model call, one attempt, 992 prompt tokens, and 307 response tokens; its regression verification rejected it. No generated recipe was activated.

### Sentry

The local `.env` contains the DSN and remains ignored by Git. A configuration smoke check reported `sentry_configured=true`, `sentry_enabled=true`, and `mode=sentry`. A fixture-backed service workflow with the real configured SDK completed successfully with `model_calls=0`, verification `PASS`, and nine emitted redacted spans:

```text
automation.check_drift
automation.execute_approved_recipe
automation.profile_csv
recipe.approve_version
recipe.compile
recipe.validate_operations
recipe.validate_schema
recipe.verify_examples
recipe.verify_invariants
```

This proves the local SDK initialization and redacted span path. Sentry dashboard receipt was not independently inspected, and the DSN must never be committed or copied into project documentation.

### Configuration hardening

An empty process environment variable no longer hides a configured non-empty `.env` value. The behavior is covered by `test_empty_process_environment_does_not_hide_env_file_values`.

## Verification-aware Gemma retry update — 2026-10-22

The model-backed compile path now uses one bounded retry budget for provider/schema failures and independent fixture-verification failures. Each schema-valid candidate is persisted and verified before another model call; failed candidates remain rejected for audit, and the active recipe is never changed automatically. Retry feedback contains only bounded stable check codes and generic messages, not CSV values or filesystem paths. The previous candidate is supplied as revision context, and prompt size is bounded.

The default fixture family is selected from the profiled input schema before model calls, so a model-generated recipe name cannot switch verification to an easier fixture family. User-authored stored fixtures still take precedence.

Actual checks after this change:

```text
python -m unittest discover -s tests -v
45 tests passed

python -m compileall -q molt tests bench.py
PASS

node --check molt/web/app.js
PASS

python bench.py
PASS — offline fixture benchmark; 2 deterministic calls avoided
```

Live Gemma was retried against `workspace/in/manual-compatible-test.csv`. The model remained unable to produce a schema-valid recipe within the configured attempts (`RECIPE_SCHEMA_INVALID`, including a malformed `drop_empty_rows` operation). No candidate was persisted or activated. This remains a safe rejection, not live compile success.

Additional live attempts used explicit mappings, decimal precision, duplicate removal, and canonical-value identity mappings. Gemma then produced structurally valid recipes, but independent verification still rejected them because the generated `map_values` mapping omitted the canonical `Food` identity mapping. The active recipe remained unchanged. This confirms the retry and rejection path; it does not establish a live Gemma candidate approval.

Sponsor environment configuration is intentionally limited to local placeholders in `.env.example`:

```text
SENTRY_DSN=<local-only Sentry DSN, never commit>
MOLT_TABPFN_ENABLED=false
MOLT_TABPFN_LICENSE_ACCEPTED=false
MOLT_TABPFN_MODEL=default
MOLT_TABPFN_DEVICE=auto
MOLT_TEMPORAL_ADDRESS=127.0.0.1:7233
MOLT_TEMPORAL_NAMESPACE=default
MOLT_TEMPORAL_TASK_QUEUE=molt
```

No additional sponsor API key is required by the current code. TabPFN requires local package/model-weight and license access rather than an environment token. Temporal requires a reachable local server rather than a sponsor key. The locally configured Sentry DSN should be regenerated if it has been exposed outside the local machine.
