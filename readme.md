# Molt

**Compile once. Verify against truth. Reuse without repeated inference.**

```text
python -m molt demo --offline --approve
```

Python 3.11+; no Ollama, credentials, or network required for this fixture demo.
`--approve` is explicit scripted demo approval, not evidence of independent
human review. Put a fresh `--state-dir` before `demo` to isolate its artifacts.

Molt is the Week 3 Hacktoberfest Open-Source AI Challenge project. It makes repetitive CSV cleanup lazy in a safer way: a local open-weight model can propose a constrained recipe, but a deterministic runtime executes it only after independent verification and human approval.

## Try the demo

From this directory:

```text
python -m molt demo --offline --approve
```

The demo shows compile, verification, approval, two deterministic reuse runs with zero additional model calls, and two drift cases that are blocked and copied to the selected workspace quarantine directory.

Developer checks: `python -m pytest -q`, `node --test tests/test_dashboard.cjs`, and `python bench.py`.

Repair candidates are deliberately separate from the active recipe:

```text
python -m molt --state-dir .molt repair-propose --recipe-file examples/recipes/expense-v1.json
python -m molt --state-dir .molt repair-verify
python -m molt --state-dir .molt repair-approve
```

The approval command refuses candidates that have not passed the complete fixture suite.

### Optional Mastra repair agent

Mastra is an optional sidecar for **repair proposals only**. It receives a
masked profile, the approved recipe and structural drift evidence through typed
read-only tools, then returns a constrained candidate. It cannot write CSVs,
activate a recipe or bypass Molt's verifier.

From the repository root:

```text
cd mastra-repair
npm install
set MOLT_MASTRA_MODEL=<your-model-id>
npm run dev
```

On PowerShell, use `$env:MOLT_MASTRA_MODEL = "<your-model-id>"` instead. Keep
the model provider credentials in the sidecar's process environment; do not put
them in `.env.example` or source control. Molt already points at
`http://127.0.0.1:4112` by default. To request a Mastra repair, call the
existing repair endpoint with `model: "mastra"` (or `mastra/<model-name>`).

The resulting candidate still follows the normal path:

```text
Mastra proposal → Molt schema validation → full regression suite → human approval
```

The sidecar currently requires you to choose a Mastra-supported model/provider.
If you want to keep repair fully local with `gemma3:4b`, give me the exact
provider/adapter you want to use for Mastra's model connection; no API key is
needed for the Molt adapter itself, but the model adapter must be configured.

## Full local MVP

### First-time setup for original use

Molt has two modes:

- **Fixture/demo mode:** uses checked-in recipes and synthetic data. It does not prove live Gemma behavior.
- **Original/live mode:** uses your own CSV inside the Molt workspace and a locally running Ollama model. The model is used only to compile or repair a recipe; approved compatible runs use zero model calls.

Molt does not require an `.env` file to start, but a real setup should use one:

```text
copy .env.example .env
```

Edit `MOLT_DATA_DIR`, `OLLAMA_BASE_URL`, and `MOLT_GEMMA_MODEL` as needed. The current default is `gemma3:4b`; the app reads these values for the API, CLI, dashboard, and Ollama adapter.

Install Ollama from the official Ollama installer, start the Ollama service, and pull the configured model:

```text
ollama pull gemma3:4b
```

Then run the readiness check:

```text
python -m molt --state-dir workspace doctor
```

For live compilation, require the model to be ready:

```text
python -m molt --state-dir workspace doctor --require-ollama
```

If Ollama is unavailable, already-approved recipes can still run deterministically. New compile and repair requests fail clearly; Molt never silently switches to a hosted model.

### Slow and steady: the compiler rejection boundary

The model proposes a recipe, not executable code. Before activation:

1. Response size/time limits apply; incomplete responses, duplicate JSON keys,
   non-finite JSON constants, and non-JSON prose are rejected.
2. The runtime checks the allowlisted operations, argument types, unique column
   names, and operation order. A model cannot substitute `trim.column` for
   `trim.columns` or invent an executable operation.
3. The input contract must fit the profiled CSV. Missing required columns and
   contradictory extra-column policies fail before a version is stored.
4. Independent expected-output/error fixtures and invariants decide whether a
   schema-valid candidate is acceptable. The model cannot author its own oracle.
5. Generation errors and verification failures share one budget: by default,
   **three requests total**, not three retries at each layer. Missing-model and
   oversized-prompt errors stop early. Attempt summaries contain codes/counts,
   not raw responses or fixture values, and are attached to the version or error.
6. A passing candidate waits for explicit approval. Rejected candidates cannot
   replace the active recipe. Compatible execution makes zero model calls.

These checks are not a proof of correctness on all inputs. Fixture coverage
matters. The historical full-expense Gemma result remains **0/5**, including the
separate bounded follow-up; this final guardrail pass did not rerun that model
experiment or claim improved generation accuracy.

### Optional TabPFN advisory analysis

TabPFN is deliberately optional and is not part of the compile/verify/reuse path. Install the extra only when this review workflow is wanted:

```text
python -m pip install -e ".[anomaly]"
```

**License:** TabPFN code and model weights have separate licenses. Prior Labs
publishes the 2.5, 2.6, 3 and 3.5 weights under **non-commercial licenses**;
commercial use requires appropriate separate permission. Earlier v2 weights
have different terms. See the [official license overview](https://github.com/PriorLabs/TabPFN#license)
and the selected checkpoint's license. Molt's config flag does not grant rights.

Enable it in `.env` only after reviewing the selected TabPFN model-weight terms:

```text
MOLT_TABPFN_ENABLED=true
MOLT_TABPFN_LICENSE_ACCEPTED=true
MOLT_TABPFN_DEVICE=auto
```

The current integration uses the supported `TabPFNClassifier` API for a narrow supervised triage flow. The anomaly-analysis request must provide a user-approved binary `label_column` and `anomaly_label`; Molt uses a deterministic stratified holdout and approved numeric, non-sensitive features. An unlabeled CSV is reported as unsupported rather than receiving invented anomaly scores. Package presence alone is not readiness: the API, configuration, license acknowledgment, model-weight access, and local hardware must all be suitable. The first real inference may require a Prior Labs login/token and model-weight download, and CPU performance may be limited.

Example request body for `POST /api/automations/{id}/anomaly-analysis`:

```json
{
  "path": "workspace/in/labeled.csv",
  "label_column": "review_label",
  "anomaly_label": "anomaly",
  "feature_columns": ["amount", "item_count"]
}
```

The response redacts row values, reports the package/config/license/readiness states, and marks the result advisory. It only scores held-out rows and never deletes, rewrites, or quarantines input rows. The core Molt workflow continues to work when TabPFN is absent, disabled, unlicensed, or unsupported.

For a live local supervised advisory check, keep the TabPFN token in the
process environment, explicitly acknowledge the selected model-weight terms,
and enable the feature for that process:

```text
MOLT_TABPFN_ENABLED=true
MOLT_TABPFN_LICENSE_ACCEPTED=true
MOLT_TABPFN_DEVICE=cpu
```

Then call the existing anomaly-analysis API with an explicit binary target and
anomaly label. Do not print or commit the token. The demonstrated synthetic
fixture result is saved in `evidence/tabpfn-temporal-live.json`.

Create a clean empty workspace for original use:

```text
python -m molt --state-dir workspace init
```

The project uses one runtime workspace. It contains the SQLite database and watched-folder directories:

```text
workspace/
├── molt.sqlite3
├── in/
├── done/
├── quarantine/
├── reports/
├── archive/
└── checkpoints/
```

Initialize the SQLite-backed demo automation:

```text
python -m molt --state-dir workspace init-demo --approve
```

Start the local API and dashboard at `http://127.0.0.1:8765/`:

```text
python -m molt --state-dir workspace serve
```

Drop compatible CSV files into `workspace/in/` and run the polling watcher in another terminal:

```text
python -m molt --state-dir workspace watch
```

The dashboard exposes real SQLite-backed automations, recipe versions, verification evidence, runs, drift reports, repair proposals, and savings metrics. The API is loopback-only and the deterministic runtime never calls the model during a compatible run.

### Optional Temporal durable execution

Temporal is an optional durable boundary around an already approved recipe. It
does not compile recipes or replace Molt's verifier. Install the SDK and run a
Temporal server plus a worker:

```text
python -m pip install -e ".[temporal]"
```

With the Temporal CLI installed, run a persistent local development server in
one terminal, then the worker in another. No Cloud account is involved:

```text
temporal server start-dev --db-filename workspace/temporal-local.sqlite
```

```text
python -m molt --state-dir workspace temporal worker
```

The default connection is `127.0.0.1:7233`, namespace `default`, task queue
`molt`. Override them with `MOLT_TEMPORAL_ADDRESS`,
`MOLT_TEMPORAL_NAMESPACE`, and `MOLT_TEMPORAL_TASK_QUEUE`. No sponsor API key
is needed for a local Temporal server. Temporal Cloud or a secured deployment
will additionally require its endpoint, TLS and authentication configuration.

Start a durable run from the CLI:

```text
python -m molt --state-dir workspace temporal start \
  --automation-id <automation-id> \
  --input workspace/in/input.csv
```

The dashboard also exposes `Run durably` for approved recipes, backed by:

```text
POST /api/automations/{id}/temporal-runs
GET  /api/temporal-runs/{workflow_id}
```

The API accepts `wait`, `workflow_id`, `activity_timeout_seconds`, `address`,
`namespace`, and `task_queue`. The workflow uses Molt's checkpointed service,
stable workflow IDs and activity retry policy. Drift is returned as a terminal
data result rather than blindly retried. The dashboard polls status and shows
the Molt outcome separately: Temporal `COMPLETED` can mean Molt `BLOCKED_DRIFT`,
not a successful CSV output. It remembers the latest workflow ID on reload;
automatic checks pause after 100 polls and Refresh checks again.

Two reproducible evidence commands (optional SDK and Temporal CLI required):

```text
python temporal_crash_recovery.py
python temporal_chaos.py
```

If the CLI is not on PATH, use `python temporal_chaos.py --temporal-cli <path>`.
The second script starts isolated local processes and uses the real HTTP API.
It kills its worker twice at deterministic checkpoint barriers, kills and
restarts its server once using the same SQLite file, then checks two compatible
files, one drift file, and an idempotent replay. It cleans up only its own
processes. Results: `evidence/temporal-chaos.json`; the smaller injected-exception
check remains in `evidence/temporal-crash-recovery.json`.

Checkpoint metadata is atomically replaced. Final service outputs are published
without replacement; a retry after output publication may reconcile identical
bytes from a completed checkpoint without rewriting them. This requires the
same retained local workspace. The demonstrated interruptions are process kills,
not power loss, concurrent multi-host writes, Cloud deployment, or production
durability. Compilation/model API calls are **outside** this Temporal workflow.

If port `8765` is already in use, choose another configured port:

```text
python -m molt --state-dir workspace serve --port 8766
```

Stop a foreground server with `Ctrl+C`. A second server cannot bind to the same port; Molt reports a `SERVER_BIND_FAILED` error instead of hiding the failure.

To use a local Ollama model instead of the checked-in fixture recipe:

```text
python -m molt demo --model gemma3:4b --approve
```

The live model response is validated against the canonical recipe schema, bounded in size/time, retried according to configuration, and never executed as code. Repair prompts include the active recipe and drift report. A live run is only demonstrated after `doctor --require-ollama` and a successful live compile.

## Why open source matters

- CSVs and recipes can stay on the user's machine.
- Ollama-supported open-weight models can be swapped without changing execution semantics.
- The generated artifact is inspectable JSON, not hidden code.
- Once approved, compatible files run offline without another inference call.
- Drift fails closed instead of silently guessing.

The bundled offline recipe is a lifecycle fixture, not evidence of live model quality. Gemma/Ollama is implemented as the local compile/repair boundary but requires a locally installed model for live evidence. TabPFN and Sentry are optional guarded integrations.

Temporal is an optional durable boundary around an already approved recipe. A
live local development server, worker, and completed fixture workflow are
documented in `evidence/tabpfn-temporal-live.json`; this does not claim live
Gemma generation through Temporal.

## Optional Temporal integration

Temporal is an isolated durable-execution adapter; the core Molt application does not import or require `temporalio`. Install it only when a Temporal worker/server workflow is wanted:

```text
pip install -e ".[temporal]"
python -m molt --state-dir workspace temporal worker
python -m molt --state-dir workspace temporal start --automation-id <id> --input workspace/in/expense-demo.csv
```

The worker activity calls the existing approved-recipe service with its database idempotency key and per-operation checkpoint directory enabled. A missing column, unmapped value, parse/type mismatch, or invariant failure is returned as `BLOCKED_DRIFT` data and is not blindly retried. Other activity failures follow the workflow's bounded retry policy. `temporal demo` is the same start flow with a short setup message; it requires a prepared approved automation, a reachable Temporal server (normally `127.0.0.1:7233`), and a worker on the `molt` task queue. Without `temporalio`, these commands return an actionable `TEMPORAL_UNAVAILABLE` error and all non-Temporal commands remain usable.

This repository does not claim a live Temporal server/worker run unless one is actually started and verified in the environment.
#   w e e k 3  
 
