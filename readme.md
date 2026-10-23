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

Developer checks: `python -m unittest discover -s tests -v` and `python bench.py`.

Repair candidates are deliberately separate from the active recipe:

```text
python -m molt --state-dir .molt repair-propose --recipe-file examples/recipes/expense-v1.json
python -m molt --state-dir .molt repair-verify
python -m molt --state-dir .molt repair-approve
```

The approval command refuses candidates that have not passed the complete fixture suite.

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
