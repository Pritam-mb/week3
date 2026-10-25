<p align="center">
  <img src="https://raw.githubusercontent.com/Pritam-mb/week3/main/evidence/hero-banner.png" alt="Molt - 0 model calls at runtime. It stops when the data changes." width="100%">
</p>

<p align="center">
  <a href="https://dev.to/challenges/hacktoberfest-week3-2026-10-19"><img src="https://img.shields.io/badge/Hacktoberfest-Week%203%20Slow%20%26%20Steady-101827?style=for-the-badge&logo=hacktoberfest" alt="Hacktoberfest Week 3"></a>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Gemma-3%3A4b-FF5722?style=for-the-badge&logo=google" alt="Gemma">
  <img src="https://img.shields.io/badge/Mastra-TypeScript%20Sidecar-purple?style=for-the-badge" alt="Mastra">
  <img src="https://img.shields.io/badge/Tests-88%20Passed-22c55e?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/Runtime%20LLM%20Calls-0-00DC82?style=for-the-badge" alt="Runtime Calls">
</p>

<h3 align="center">
  Compile once. Verify against truth. Reuse forever without repeated inference.
</h3>

---

## What is Molt?

Every month the same expense export lands with the same problems: whitespace on merchant names, three different date formats, amounts formatted as `"$1,240.00"` strings, and inconsistent categories.

Piping recurring CSV files through an LLM is expensive, non-deterministic, and prone to silent data corruption. **Molt inverts the pattern: use the model as an offline compiler, never a production runtime.**

* **Phase 1 (Compile Once):** A local Gemma model (`gemma3:4b` via Ollama) inspects a masked schema profile (column names and types only, zero raw cell rows) and emits a recipe constrained to a closed 9-operation allowlist.
* **The Verifier Gate:** Independent golden fixtures, null-injection checks, row-count invariants, and idempotence tests (`apply(apply(x)) == apply(x)`) validate the candidate before human approval.
* **Phase 2 (Run Forever):** Approved recipes execute in pure Python. Steady-state execution takes **~16 milliseconds** and makes **zero model calls**.
* **Contract Drift Guard:** If a vendor export changes (e.g. missing column), a pure-Python contract check blocks the run in 16ms and quarantines the file before bad rows reach disk.
* **Out-of-Band Repair:** An isolated **Mastra** TypeScript agent proposes candidate fixes using Groq (`openai/gpt-oss-120b`). Fixes are held inactive until independent regression tests pass and an operator explicitly approves.

---

## Drift Benchmark: Naive Script vs. Molt

In a four-case drift benchmark against a naive positional cleanup script:

| Metric | Naive Script Baseline | Molt Runtime Guard |
| :--- | :---: | :---: |
| **Silent Wrong Outputs** | **3** | **0** |
| **Drift Cases Accepted Without Validation** | 2 | 0 |
| **Blocked Drift Cases** | 0 | **2 (Quarantined in 16ms)** |
| **Runtime Model Calls** | 0 | **0** |
| **Mean Latency** | 1.82 ms | 3.97 ms |

```json
// From evidence/benchmark.json:
{
  "naive_positional_script_baseline": {
    "case_count": 4,
    "silent_wrong_outputs": 3,
    "drift_cases_accepted_without_validation": 2
  },
  "molt_drift_measurement": {
    "case_count": 4,
    "silent_wrong_outputs": 0,
    "blocked_drift_cases": 2,
    "runtime_model_calls": 0,
    "mean_latency_ms": 3.968
  }
}
```

---

## Architecture

```text
======================================================================================================
                                    MOLT: COMPILE ONCE, RUN FOREVER
======================================================================================================

 [ PHASE 1: COMPILE ONCE ]                                      [ VERIFICATION & APPROVAL GATE ]
 -------------------------                                      --------------------------------
  Raw CSV Export (in/)                                            Candidate Recipe v1 (JSON)
           │                                                                 │
           ▼                                                                 ▼
 ┌──────────────────────┐   Masked Profile (Headers/Dtypes)    ┌────────────────────────────────────┐
 │  CSV Profiler        │ ───────────────────────────────────▶ │  Independent Verifier Gate         │
 │  (molt/application)  │  *ZERO raw cell rows or PII*         │  • Closed 9-Op Allowlist Check     │
 └──────────────────────┘                                      │  • Golden Input/Output Fixtures    │
                                                               │  • Row-Count & Null Invariants     │
 ┌──────────────────────┐                                      │  • Idempotence: f(f(x)) == f(x)    │
 │  Local Gemma 3:4b    │ ───────────────────────────────────▶ └─────────────────┬──────────────────┘
 │  (Ollama via HTTP)   │  Constrained JSON Recipe DSL                           │
 └──────────────────────┘  *Cannot emit Python or shell*                         ▼ (Pass: 6/6)
                                                               ┌────────────────────────────────────┐
                                                               │  Explicit Human Approval           │
                                                               │  [Accept & Activate Recipe v1]     │
                                                               └─────────────────┬──────────────────┘
                                                                                 │
 ════════════════════════════════════════════════════════════════════════════════╪════════════════════
                                                                                 │
 [ PHASE 2: RUN FOREVER (DETERMINISTIC STEADY STATE) ]                           ▼
 -----------------------------------------------------                 Active Recipe v1 Store
  New Incoming File (in/)                                                        │
           │                                                                     │
           ▼                                                                     │
 ┌──────────────────────────────────────────┐                                    │
 │  Contract Drift Check (16ms)             │ ◀──────────────────────────────────┘
 │  • Required columns match?               │
 └─────────────────────┬────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
  [ Compatible: PASS ]        [ Drift Detected: FAIL ]
         │                           │
         ▼                           ▼
 ┌───────────────────────────┐ ┌───────────────────────────┐
 │ Pure Python Engine        │ │ Quarantine & Block (16ms) │
 │ (molt/core.py)            │ │ • Moved to quarantine/    │
 │ • Reuses approved recipe  │ │ • SHA-256 Fingerprinted   │
 │ • ~16ms execution latency │ │ • Audit bead turns RED    │
 │ • 0 RUNTIME MODEL CALLS   │ └─────────────┬─────────────┘
 └─────────────┬─────────────┘               │
               │                             │
 ┌─────────────▼─────────────┐               │ [ OUT-OF-BAND REPAIR FLOW ]
 │ Temporal Worker Checkpoint│               ▼
 │ • Durable state barrier   │ ┌────────────────────────────────────────────────────────┐
 │ • Crash replay resilience │ │ Mastra Repair Sidecar (:4112 / Groq openai/gpt-oss)    │
 └─────────────┬─────────────┘ │ • Out-of-band TypeScript agent receives masked diff    │
               │               │ • Proposes candidate Recipe v2 (stored as INACTIVE)   │
 ┌─────────────▼─────────────┐ └────────────────────────────┬───────────────────────────┘
 │ Atomic Write to done/     │                              │
 │ • Zero duplicate rows     │                              ▼
 │ • Graph: +1 Call Avoided  │ ┌────────────────────────────────────────────────────────┐
 └───────────────────────────┘ │ Verifier Regression (6/6) ──▶ Human Accepts Recipe v2 │
                               └────────────────────────────────────────────────────────┘

 ═════════════════════════════════════════════════════════════════════════════════════════════════════
 [ CROSS-CUTTING PRIVACY & OBSERVABILITY BOUNDARY ]
 ──────────────────────────────────────────────────
  ┌──────────────────────────────────────────────┐  ┌───────────────────────────────────────────────┐
  │ Sentry 9-Stage Agent Tracing                 │  │ TabPFN Local CPU Anomaly Scorer               │
  │ • 9 Spans: profile ──▶ verify ──▶ execute    │  │ • 1,500 Synthetic Expense Holdout Rows        │
  │ • Strict Allowlist: _SAFE_ATTRIBUTE_KEYS     │  │ • 94.55% Precision / 72.22% Recall            │
  │ • Scrub Hook: send_default_pii=False         │  │ • Strictly Advisory: Never Alters Source Bytes│
  │ • Zero raw rows or secrets sent to APM       │  │ • Local CPU only (telemetry_enabled: false)   │
  └──────────────────────────────────────────────┘  └───────────────────────────────────────────────┘
======================================================================================================
```

---

## Quickstart in 30 Seconds

No API key, no Ollama installation, and no external network required for the offline fixture demo.

### 1. Instant Offline Demo
```bash
python -m molt demo --offline --approve
```
*Executes four benchmark cases: 2 clean batches processed deterministically, 2 drifted batches halted and quarantined, exactly 0 execution model calls.*

### 2. Live Local Bento Dashboard
```bash
python -m molt --state-dir workspace serve --host 127.0.0.1 --port 8765
```
Open [`http://127.0.0.1:8765/`](http://127.0.0.1:8765/) in your browser.
- **Run Beads:** Every run decision represented as a persistent green/red audit bead.
- **Calls Avoided Ledger:** Live real-time counter of LLM inferences saved.
- **Safe Evidence Diff:** Structural-only error diagnostics at `http://127.0.0.1:8765/diff.html`.

### 3. Run the Automated Test Suite
```bash
# Python test suite (79 tests, 20 subtests)
python -m unittest discover tests

# Web UI dashboard and safe diff tests (9 tests)
node tests/test_dashboard.cjs
node tests/test_diff_page.cjs
```
All **88 tests pass cleanly** out of the box.

---

## The Closed 9-Operation Allowlist

Molt's compiler client and execution engine reject any operation not explicitly defined on this allowlist. A model **cannot** emit arbitrary Python, shell commands, or unapproved transforms:

| Operation | Arguments | Description |
| :--- | :--- | :--- |
| `trim` | `columns: list[str]` | Strips leading and trailing whitespace. |
| `rename_column` | `from: str, to: str` | Renames header according to canonical schema. |
| `parse_date` | `column: str, formats: list[str]` | Parses varying date strings into ISO-8601 (`YYYY-MM-DD`). |
| `parse_decimal` | `column: str` | Strips currency symbols (`$`, `,`) and normalizes numbers to 2 decimal places. |
| `map_values` | `column: str, mapping: dict` | Standardizes categorical values (e.g. `{"Food": "F&B", "food": "F&B"}`). |
| `split_column` | `column: str, delimiter: str, new_columns: list[str]` | Deterministically splits a delimited column. |
| `select_columns`| `columns: list[str]` | Retains only approved columns in guaranteed order. |
| `reorder_columns`| `columns: list[str]` | Enforces exact physical column sequence. |
| `dedupe` | `columns: list[str]` | Drops duplicate rows using a specified key column. |

---

## Live Model Compilation & Out-of-Band Repair

### 1. Local Gemma 3:4b Compilation
Start your local Ollama instance and pull the model:
```bash
ollama pull gemma3:4b
python -m molt --state-dir workspace doctor --require-ollama
python -m molt demo --model gemma3:4b --approve
```

#### The Gemma Failure Ladder: Why We Don't Trust Models Unconditionally
We tested `gemma3:4b` on a difficulty ladder (5 trials per rung). On the full 6-operation task, the model achieved **0/5**:
* In one run, Gemma's natural-language summary claimed it parsed amounts, but its emitted JSON omitted the decimal transform entirely.
* **Molt's verifier caught the discrepancy immediately and failed the golden check before anything could execute:**

```json
// From evidence/gemma-rung3-rejected-candidate.json:
{
  "recipe": {
    "name": "Trim, Normalize Date, Parse Decimal",
    "description": "Trims whitespace from merchant, normalizes date to YYYY-MM-DD, and parses amount to two decimal places.",
    "operations": [
      {
        "type": "trim",
        "columns": ["merchant"]
      }
    ]
  },
  "rung": 3,
  "verification": {
    "status": "FAIL",
    "failed_checks": 1,
    "failed_check_codes": ["golden_output"]
  }
}
```

### 2. Mastra TypeScript Repair Sidecar
When data drifts (e.g., vendor drops a column), repair runs **out of band**:
```bash
cd mastra-repair
npm install
npm run dev
```
- Listens on `http://127.0.0.1:4112`.
- Receives only the active recipe, masked profile, and structural error (**zero customer PII or raw CSV rows**).
- Powered by Groq (`openai/gpt-oss-120b`), Mastra proposes an updated candidate recipe.
- Molt stores the candidate as **INACTIVE** until the regression suite passes (6/6 checks) and an operator explicitly clicks `[Accept repair]`.

---

## Partner Integrations

### 1. Temporal: Crash Resilience & Checkpoint Recovery
Wraps steady-state execution so that injected process kills mid-flight (`MOLT_CRASH_AT=1`, killing worker and server) resume from the last saved checkpoint with **zero duplicate writes and zero model calls**:

```json
// From evidence/temporal-crash-recovery.json:
{
  "status": "COMPLETE",
  "workflow": {
    "result_status": "SUCCEEDED",
    "temporal_outcome": "completed",
    "llm_calls": 0,
    "rows_read": 4,
    "rows_written": 3
  },
  "failure_injection": {
    "mode": "MOLT_CRASH_AT",
    "after_step": 1,
    "activity_attempts": 2,
    "checkpoint_created": true,
    "checkpoint_resumed": true
  }
}
```

### 2. TabPFN: Local CPU Advisory Anomaly Scorer
Runs locally on CPU (`tabpfn==9.1.0`) across 1,500 synthetic expense rows (1,200 training, 300 held-out test rows). It flags statistical outliers with **94.55% precision** without altering a single byte of source data:

```json
// From evidence/tabpfn-accuracy.json:
{
  "task": "supervised_binary_classification",
  "dataset": { "rows": 1500, "train_rows": 1200, "held_out_rows": 300 },
  "holdout_metrics": {
    "confusion_matrix": {
      "true_positives": 52,
      "false_positives": 3,
      "true_negatives": 225,
      "false_negatives": 20
    },
    "precision": 0.9455,
    "recall": 0.7222,
    "accuracy": 0.9233
  },
  "source_rows_changed": 0,
  "advisory_only": true
}
```
*Why 72% recall?* TabPFN is strictly advisory triage. The deterministic contract gate is what provides absolute correctness guarantees.

### 3. Sentry: 9-Stage Distributed Tracing & Strict Redaction
Instruments all 9 pipeline stages (`automation.profile_csv` through `automation.execute_approved_recipe`). Enforces strict payload redaction in [`molt/telemetry.py`](molt/telemetry.py):

```python
_SAFE_ATTRIBUTE_KEYS = {
    "attempt", "checks_passed", "checks_total", "column_count",
    "input_bytes", "input_rows", "model_calls", "output_rows", "status"
}
_SENSITIVE_KEY_PARTS = (
    "content", "csv", "file", "path", "prompt", "response", "row", "secret", "token", "value"
)
```

The Sentry SDK initializes with `send_default_pii=False` and hooks `before_send` to strip prompts, paths, and cell strings before network dispatch. When `SENTRY_DSN` is empty, Molt operates in 100% offline local-only mode.

<p align="center">
  <img src="https://raw.githubusercontent.com/Pritam-mb/week3/main/evidence/sentry-trace.png" alt="Sentry 9-Stage Distributed Trace Waterfall" width="100%">
  <em>Figure: Real live Sentry waterfall trace for molt showing all 9 lifecycle stages executing deterministically in ~50ms.</em>
</p>

---

## Directory Structure

```text
week3/
├── molt/                       # Core Python deterministic runtime
│   ├── core.py                 # Pure-Python transform engine & atomic writes
│   ├── application.py          # State machine, verification gates & contracts
│   ├── ollama.py               # Local Gemma compilation adapter
│   ├── temporal.py             # Durable Temporal workflow & worker
│   ├── anomaly.py              # Local TabPFN advisory adapter
│   ├── telemetry.py            # Sentry tracing adapter & redaction filter
│   └── web/                    # Bento dashboard UI (HTML/CSS/JS, zero CDN deps)
├── mastra-repair/              # Isolated Mastra TypeScript sidecar
│   ├── src/                    # Mastra tools, agent & Groq integration
│   └── package.json
├── tests/                      # 88 automated unit, integration, and UI tests
├── evidence/                   # Machine-readable JSON benchmarks & screenshots
├── workspace/                  # Runtime state dir (in/, done/, quarantine/)
├── POST_SUBMISSION_READY.md    # Official DEV.to submission post
└── README.md
```

---

## Verification Snapshot

Recorded October 25, 2026:

| Check | Result | Details |
| :--- | :---: | :--- |
| **Python Test Suite** | **79 PASSED (20 subtests)** | Full core, application, and verifier suite |
| **Web UI & Diff Tests (Node)** | **9 PASSED** | Dashboard lifecycle and safe evidence diff integrity |
| **Mastra TypeScript Build** | **PASSED** | Clean `tsc --noEmit` |
| **Gemma Local Compile Gate** | **PASSED** | Envelopes, operation schemas, and profile contract gates |
| **Mastra Live Repair** | **PASSED** | 6/6 verifier regression checks passed |
| **Temporal Chaos Recovery** | **PASSED** | Deterministic checkpoint resume, zero duplicate writes |
| **TabPFN CPU Evaluation** | **PASSED** | 94.55% precision, confusion matrix disclosed |
| **Sentry Redaction** | **PASSED** | Strict allowlist verified in unit tests |
| **Offline Submission Check** | **PASSED** | 0 model calls, clean execution + quarantine |
| **Drift Benchmark** | **PASSED** | 0 silent errors vs. 3 naive script errors |

---

## License

This project is licensed under the [MIT License](LICENSE).
TabPFN model weights are subject to Prior Labs non-commercial licensing terms.
