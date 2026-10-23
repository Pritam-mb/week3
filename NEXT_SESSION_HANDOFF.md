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

The model-backed compile path now retries schema-valid candidates after independent verification failures with bounded redacted feedback; failed candidates remain rejected and inactive. Model-backed repairs now use the same verified retry path and preserve the active recipe. A fresh live compile after this change still returned `RECIPE_SCHEMA_INVALID` within its configured attempts, so no live Gemma candidate is approved. Keep Gemma candidates and repairs inactive unless they pass the full fixture suite. If sponsor evidence is still needed, inspect the Sentry dashboard for the redacted smoke trace without exposing row data. Do not enable TabPFN until the supported labeled task, license/model-weight access, and safe feature columns are explicitly confirmed.

## Next-session handoff — 2026-10-23 (stop point)

### User's current goal

The user wants Molt presented as a full lifecycle for learning a repeated task once and then executing a verified deterministic program, not merely as a CSV cleaner:

```text
teach once → local Gemma proposes → tests decide → human approves → zero-call reuse → drift blocks → repair is verified and approved
```

The deadline is Sunday 2026-10-25. Tomorrow's priority is proof and submission material, not adding unrelated features.

### Current state

- Core workflow, SQLite audit trail, local API, dashboard, deterministic execution, drift quarantine, repair approval, Sentry adapter, and Gemma/Ollama integration are implemented.
- Gemma compile retries and model-backed repair retries are verification-aware. Invalid candidates remain rejected; the active version is not overwritten.
- Live Ollama readiness is confirmed: Ollama `0.40.8`, model `gemma3:4b`, endpoint `http://127.0.0.1:11434`.
- Multiple live explicit-mapping Gemma attempts produced valid recipes, but verification rejected them. The latest failures had correct golden output but omitted canonical `Food -> Food` identity mapping under `on_unmapped: fail`. No live Gemma recipe has passed, been approved, and then run with `llm_calls=0`.
- The requested `keep_known: true` recipe operation behavior is **not implemented yet**. This is tomorrow's first code task. Do not solve the identity-mapping problem by weakening verification.
- Synthetic TabPFN data was generated by the user-provided `dataset.py`:
  - `molt_drift_features.csv` at the repository root (untracked)
  - `workspace/molt_drift_features.csv` for Molt analysis (runtime data)
  - 1,500 rows and 358 positive drift labels (24%) with seed 7
- TabPFN package is installed. The local `.env` contains a `TABPFN_TOKEN`; do not print, copy, commit, or include it in this handoff. The first live attempt needed the process environment variable and opened the Prior Labs authentication flow; the user aborted it after the CPU/download warning. There is no completed TabPFN inference evidence yet.
- TabPFN should remain disabled in the normal project configuration unless tomorrow's real inference is completed and documented. It is optional and should not displace the Gemma proof.
- The dashboard currently remains the existing dependency-free dashboard in `molt/web/`. The replacement `web/` HTML/JS files referenced by the user were not present in the workspace; only the visual CSS/JS specification was pasted into chat. Do not claim the new pipeline graph is integrated until actual files are available or implemented.
- Sentry is configured locally, but the dashboard trace has not been visually inspected. The DSN was exposed earlier and must be rotated after any screenshot/evidence capture.

### First task tomorrow: remove the Gemma identity-mapping failure

Implement and test `keep_known` for `map_values`:

1. Add `keep_known` to the recipe schema and operation validation, defaulting to `true` for backward-compatible recipes.
2. Define known values from the mapping outputs (or an explicit allowed-values set if that is the chosen contract). If an input value is already a canonical mapped value, pass it through when `keep_known` is true.
3. Unknown values must still follow `on_unmapped`; with `fail`, they must still block execution.
4. Normalize/fill defaults before verification and persist the normalized recipe as the tested recipe. Do not normalize after a pass.
5. Add tests for canonical pass-through, unknown-value blocking, backward compatibility, and live-style recipe verification.
6. Tighten the retry feedback to report safe structural data such as `unmapped value in column category, 3 rows`; never send raw cell values.

Then run one simple live Gemma task first. If the full expense task still fails, use a simpler task with no category mapping so there is a real approved live recipe and zero-call deterministic run before attempting the larger task.

### Second task tomorrow: measure Gemma honestly

Run 5–10 repeated live attempts for one or more fixed tasks. Record in a workspace report, without prompts or secrets:

```text
model tag
task name
attempt number
pass on first candidate (pass@1)
pass within configured verified retries (pass@N)
rejected/exhausted
total model calls
verification result
```

Do not invent pass-rate numbers for the post. A failed candidate is useful evidence if it remains rejected.

### Third task tomorrow: benchmark the actual story

Inspect `bench.py`. Add or verify an independently authored naive positional-script baseline with:

- renamed-column drift;
- dropped-column drift;
- extra/reordered-column drift;
- silent wrong outputs from the naive baseline;
- Molt quarantined/blocked counts;
- repair approval count if included.

The expected outputs must not be generated by executing the Molt recipe being measured. Use a fixed seed and one repeatable command. Keep the claim boundary honest: model-call avoidance is not measured electricity savings.

### Dashboard/submission decision

The user supplied a visual style and an `fromApi()` mapping prompt, but not actual replacement `web/` files. Tomorrow:

- If the files are provided, replace `molt/web/index.html`, `molt/web/style.css`, and `molt/web/app.js`, adapting only the API mapping as requested.
- If they are not provided, do not spend the deadline rebuilding the dashboard. Capture evidence from the existing dashboard and state the visual panel is not shown.
- Never show raw CSV values, local paths, prompts, model responses, tokens, or Sentry DSNs in screenshots.

### Sponsor decisions

- Gemma: claim only after a live candidate passes, is human-approved, and a later compatible run proves `llm_calls=0`.
- Sentry: inspect the real trace, verify redaction by eye, capture evidence, then rotate the DSN.
- TabPFN: only claim a live advisory inference if the token/license flow completes and a real result is captured. Synthetic data must be labeled as synthetic and rule-generated; it does not prove real-world drift value. If blocked, write `implemented, not demonstrated`.
- Temporal: cut unless a live server/resume demo can be completed in under 45 minutes. Do not spend the main deadline on it.

### Submission writing

Start the post no later than Saturday afternoon. Use one story: compiled task → verification → human approval → zero-call reuse → drift block → verified repair. Include one rejected Gemma candidate, the actual benchmark table, actual pass@1/pass@N numbers, and explicit limits. Use tags `#devchallenge` and `#hf26challenge`. Do not claim "first", "unprecedented", or a general agent.

### Exact checks already passed at this stop point

Run from `D:\week3`:

```text
python -m unittest discover -s tests -v
PASS — 46 tests

python -m compileall -q molt tests bench.py
PASS

node --check molt/web/app.js
PASS

python bench.py
PASS — offline fixture benchmark

python -m molt --state-dir workspace doctor --require-ollama
PASS — Ollama server/model and telemetry configured; TabPFN disabled
```

Dashboard smoke endpoints returned HTTP 200:

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/api/health
http://127.0.0.1:8765/api/config
http://127.0.0.1:8765/api/metrics
http://127.0.0.1:8765/api/metrics/ledger
http://127.0.0.1:8765/api/automations
```

### Working tree at stop

At the stop point, `git status --short` showed only this handoff file modified plus two untracked files: the user-provided `dataset.py` and generated root `molt_drift_features.csv`. The prior Gemma retry/privacy/repair implementation is present in the current committed revision `b012502`. Do not reset or discard it. Decide tomorrow whether to keep the generator and ignore/remove the generated artifact. The local `.env` is private and must remain uncommitted.

### One concrete next action

Open `molt/core.py`, `molt/ollama.py`, and `molt/application.py`; implement `map_values.keep_known` with tests first, then run a simple live Gemma compile and deterministic approved run. Stop adding features if that proof is not complete; switch to evidence capture and post writing.

## Session update — 2026-10-23

### Completed first task

- Implemented `map_values.keep_known` in `molt/core.py`.
- Recipes are normalized before validation, execution, verification, and persistence; omitted `keep_known` defaults to `true`.
- Canonical values are defined from mapping outputs and pass through when `keep_known` is enabled.
- Unknown values still obey `on_unmapped`; fail-mode execution now reports only the column and unmapped row count.
- Added the field to the Ollama schema/instructions and updated safe retry feedback to exclude raw values.
- Added regression tests for canonical pass-through, explicit rejection, backward-compatible normalization, persistence before verification, and redacted structural feedback.

### Live Gemma evidence

- A full expense compile was attempted with local `gemma3:4b`; the first run exhausted the 30-second timeout budget, and a second one-call run produced a rejected candidate because Gemma added an incompatible category casing operation. No invalid candidate was approved.
- A simpler live task then passed: one local Gemma call proposed merchant trimming, independent custom fixture verification passed, the candidate was human-approved in the script, and the deterministic run succeeded with `llm_calls=0` and 4 rows written.
- Live simple-task metadata: model `gemma3:4b`, endpoint `http://127.0.0.1:11434`, 1 attempt, 1 model call, 1,399 prompt tokens, 123 response tokens, verification `PASS`.
- The successful live automation/version remain in the local `workspace` SQLite state for evidence inspection. The custom expected fixture is runtime workspace data and is not a repository source artifact.

### Checks after this session

```text
python -m unittest discover -s tests -v
PASS — 50 tests in 83.813 seconds

python -m compileall -q molt tests bench.py
PASS

node --check molt/web/app.js
PASS

python bench.py
PASS — offline fixture benchmark; 2 steady-state calls avoided, with the stated inference-proxy claim boundary

python -m molt --state-dir workspace doctor --require-ollama
PASS — Ollama server/model ready, telemetry configured, TabPFN disabled
```

### Next concrete action

Do not revisit `keep_known` unless a regression appears. Inspect the successful live automation and capture sanitized lifecycle evidence: approved recipe, verification result, zero-call run, and the earlier rejected Gemma candidate. Then run the planned 5–10 fixed-task attempts and record actual pass@1/pass@N results in a workspace report without prompts, secrets, raw CSV values, or local credentials. Keep TabPFN disabled unless its labeled task, licensing/access, and safe feature columns are explicitly confirmed.

The first automated 5-attempt measurement was started with a 120-second model timeout but exceeded the command's 15-minute execution limit before writing its report; no pass-rate result should be inferred from that attempt. Re-run it with fewer attempts or a bounded per-attempt timeout and confirm the report file exists before using any numbers.

## Refinement-plan update — 2026-10-23

- Added the Tier A4 benchmark baseline in `bench.py` and `tests/test_bench.py`.
  It uses seed 41, an independent positional script, four drift cases, silent-wrong output counts, and measured Molt block/quarantine counts.
- Added `evidence/` with sanitized lifecycle, benchmark, Gemma ladder, rejected-candidate, and passing-recipe artifacts.
- Prompt A2 refinement was applied: Gemma is explicitly told not to invent casing or other operations that were not requested.
- Real task-ladder results are saved in `evidence/gemma-ladder.csv`:
  - Rung 1 trim merchant: pass@1 5/5, within configured retries 5/5.
  - Rung 2 trim plus dates: pass@1 4/5, within configured retries 5/5.
  - Rung 3 trim plus dates plus decimals: pass@1 3/5, within configured retries 4/5; one exhausted rejection.
  - Rung 4 full expense: 0/5; all five attempts timed out before a provider response envelope. Model-call count is intentionally unknown, not zero.
- The post outline and Tier A status are now in `GAPS_AND_FIXES.md` section 8.

## TabPFN and Temporal update — 2026-10-24

- TabPFN live supervised advisory inference completed using the inherited local
  token without printing or recording it. On the synthetic labeled fixture,
  1,200 train rows and 300 held-out rows were used; 55 held-out rows were
  flagged, `rows_changed=0`, and the source was preserved. Evidence:
  `evidence/tabpfn-temporal-live.json`.
- Installed the optional `temporalio` SDK from `.[temporal]`.
- Downloaded the Temporal CLI into the approved temp directory, started a
  local development server, started a Molt worker, and completed workflow
  `molt-live-20261024-001`.
- Temporal result: `SUCCEEDED`, `temporal_outcome=completed`, 11 history events,
  0 model calls, 4 rows read, 3 rows written. This used the approved fixture
  recipe and is evidence for the durable boundary, not live Gemma generation.
- Fixed a real Temporal integration bug in `molt/temporal.py`: the decorated
  activity was synchronous, which the current SDK rejects without a custom
  executor. It is now an async activity that runs the existing synchronous
  service in `asyncio.to_thread`.
- The local worker/server are still running outside the workspace. Inspect
  the process/listening port before reuse; do not claim a fresh workflow unless
  it is actually queried.

### Next concrete action after this refinement pass

Run the new benchmark tests and full suite, inspect `evidence/benchmark.json` and `evidence/lifecycle.json` for privacy, then decide whether there is enough time for Tier B1 verifier-catch-rate measurement. Do not start dashboard polish or new integrations before the post draft exists.

That action is now complete: benchmark tests and the full suite passed, the
evidence JSON parsed cleanly, B1 measured 18/20 caught with two documented
misses, and `POST_DRAFT.md` exists. Remaining work is post review/capture only:
optionally implement B2 plain-language approval summary if there is a clear
time budget, otherwise leave it deferred and use the existing dashboard. Do
not add Tier C polish until the draft is reviewed and any screenshots are
sanitized.

## Submission pass — 2026-10-24 (latest, supersedes earlier next steps)

Stop new features. `POST_DRAFT.md` has been audited and now distinguishes live
Gemma evidence, scripted approval, and separate fixture drift/repair records.
The pipeline illustration is available as `evidence/pipeline.svg` and the
visually inspected browser-rendered `evidence/pipeline.png`.

- Verifier fixes: new dedupe-key fixture and expected-error unknown-category
  oracle wired into the expense default verification path. Original 20 mutations
  recovered exactly from the inline session command. Original fixtures reproduce
  18/20; expanded fixtures reject 20/20, including five schema errors. Correct
  recipe passes 11/11. `python verifier_measurement.py --check` reproduces it.
- TabPFN: real synthetic holdout confusion TP52/FP3/TN225/FN20; precision94.55%,
  recall72.22%; source hash preserved. `evidence/tabpfn-accuracy.json`.
- Full-task final bounded attempt: warm Gemma, shorter prompt,120s request timeout,
  five trials with three requests each. 0/5 successes, one request timeout,
  14 schema-valid candidates rejected. No activation. Original ladder unchanged.
  Two report writes failed on Windows; outcomes recovered from existing SQLite
  records without rerunning calls; total latencies left unavailable. No staged
  compilation added. `evidence/gemma-full-task-followup.json`.
- Full suite: 66 tests passed; compileall, JS syntax, benchmark, mutation rerun
  and diff whitespace checks passed. Offline demo passed in a fresh temporary
  workspace without credentials/.env and with socket connections forbidden.
- Hygiene: `.env` ignored/not tracked; no current token/DSN value found in all
  reachable Git blobs. Historical credential-shaped strings found in workflow.txt
  and older .env.example; workflow.txt still contains a match. DO NOT publish
  until privately reviewed/revoked if real. Do not paste strings into chat.
- No Sentry dashboard access/rotation performed. No Temporal UI screenshot
  (headless server). No publication or independent human post review.

Next action: address the credential warning and manual account/capture checklist
in `evidence/CAPTURE_CHECKLIST.md`, then review/upload `POST_DRAFT.md` and its
PNG in the publishing preview. Every numeric claim maps to
`evidence/POST_AUDIT.md`. Do not repeat the full-task experiment or expand scope.
