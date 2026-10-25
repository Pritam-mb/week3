This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19).

# I Taught a Local 4B Model One CSV Chore. It Hasn't Been Called Since.

Here is the number that matters. I ran a four-case drift benchmark against a naive positional cleanup script—the kind everybody writes at 11pm and then forgets about. The script produced **three silently wrong outputs**. Molt produced **zero**: it processed the clean files and refused the drifted ones before a single bad row reached disk.

Steady-state execution takes about **16 milliseconds** and makes **zero model calls**.

The model ran once, at the beginning, and hasn't been needed since. That is the entire point.

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

## What I Built: The Chore

Every month the same expense export lands in the same folder with the same four problems: whitespace on merchant names, three different date formats, amounts formatted as `"$1,240.00"` strings, and a category column that uses `Food`, `food`, and `F&B` interchangeably.

Twenty minutes of repetitive manual drudgery.

The obvious 2026 fix is to pipe the file through an LLM. I didn't want to, for three reasons:
1. **Per-file cost:** It costs money on every run, forever.
2. **Non-deterministic:** The same file can produce different outputs twice.
3. **Quiet failure:** A model that mis-parses one date out of four hundred hands you a clean-looking CSV with a wrong number in it, and you only find out at quarter close.

So I inverted it: **use the model as a compiler, not a runtime.**

---

## Compile Once, Run Forever

Molt splits the job into two phases that never touch each other:

* **Phase one (once):** A local Gemma model (`gemma3:4b` via Ollama) looks at a *masked schema profile*—column names and inferred types, never a single raw row—and emits a JSON recipe constrained to a closed operation allowlist: `trim`, `parse_date`, `parse_decimal`, `map_values`, `split_column`, `select_columns`, `dedupe`. It cannot emit Python. It cannot emit shell. If it proposes an op that isn't on the list, the recipe is rejected before anything runs.
* **The Verifier Gate:** That recipe then has to survive an independent verifier—golden fixtures written by hand, row-count invariants, null-injection checks, and an idempotence test (`apply(apply(x)) == apply(x)`)—and then it has to survive an explicit human approval click.
* **Phase two (forever):** Approved recipes execute in pure Python. No model, no network, no tokens, no variance. Same input, same output, every time.

![Molt Architecture & Verification Pipeline](https://raw.githubusercontent.com/Pritam-mb/week3/main/evidence/pipeline.png)
*Figure 1: Raw data stays inside the local deterministic runtime. Only masked metadata ever reaches a model.*

---

## The Lazy Payoff

Drop a file in `in/`. Molt fingerprints its schema, matches the approved recipe, runs it, writes the result atomically to `done/`, and logs the run. 

You weren't there. You don't need to have been there.

That's the sloth version of automation: expend energy once, deliberately, on the part that actually needs thinking, and then coast on near-zero energy indefinitely. The counter on the dashboard that reads *model calls avoided* is really a counter of mornings I didn't spend babysitting a data script.

![Molt Bento Dashboard](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/o4kpuveos85uuu8yeo4n.png)
*Figure 2: Run beads, the calls-avoided ledger, the seven-stage lifecycle stepper, and the active recipe under review.*

---

## When the Data Changes: The Complete Drift & Repair Flow

Deterministic automation has one classic failure mode: the vendor changes the export, your script keeps running, and it silently produces garbage. This is the exact problem Molt was built to solve.

Here is the exact step-by-step visual lifecycle of what happens when data drifts:

### 1. Drift Detected, Run Blocked in 16ms
A file arrived missing the `notes` column. Molt did not guess. It did not impute. It did not ask a model to invent a value. A pure-Python contract check caught it in 16ms, moved the file to `quarantine/` with a SHA-256 fingerprint, and turned the run bead permanently red.

![Why Molt blocked this file](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/cktiwawjavsb2odjh0lg.png)
*Figure 3: Run 2 tripped REQUIRED_COLUMN_MISSING. The timeline highlights the red audit bead, the status panel details the error, and the out-of-band "Suggest Mastra repair" button is revealed.*

The evidence diff page shows what was expected, what arrived, and the exact contract rule that fired—structural metadata only, zero raw financial values rendered:

![Safe Evidence Diff for Blocked Drift](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/6dwsn1lf5pglrnzc9zme.png)
*Figure 4: The Safe Evidence Diff report for the blocked run. Displays observed headers vs. required contract, audit decision trace, and approved recipe limits.*

---

### 2. Mastra Agent Proposes, Regression Tests Verify
Repair happens **out of band**, which is the most critical design decision in the project:
1. The operator clicks **`[Suggest Mastra repair]`**.
2. A **Mastra** agent runs as an isolated TypeScript service on its own port (`mastra-repair/` on port 4112).
3. It receives the active recipe, the masked profile, and the structural error—**zero customer PII or raw CSV rows**.
4. Powered by Groq (`openai/gpt-oss-120b`), Mastra proposes a candidate recipe removing the obsolete `notes` requirement while preserving every formatting rule.
5. The candidate is stored as an inactive draft, advancing the lifecycle stepper: `1. Drift blocked` -> `2. Ask Mastra` -> `3. Candidate stored`.

![Mastra repair candidate stored and awaiting tests](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/ls5m6h0wmy4oqwbqsjtn.png)
*Figure 5: Mastra proposed a repair. The candidate is stored separately and remains completely inactive until independent regression tests pass and a human explicitly approves.*

6. The operator clicks **`[Run repair tests]`**. Molt ignores the agent's opinion of its own work and executes the full regression suite: **6/6 checks passed**.

---

### 3. Human Operator Reviews & Accepts the Repair
Molt **never auto-promotes** an unreviewed candidate. The operator reviews the four-line JSON diff in the dashboard:

```text
[Candidate Recipe v2 Review]
- Required columns: ["date", "merchant", "amount", "category", "notes"]
+ Required columns: ["date", "merchant", "amount", "category"]
Status: VERIFIED (6/6 checks passed). Waiting for human acceptance.
```

The operator clicks **`[Accept repair]`**. The candidate is promoted to **Recipe v2 (Active)**.

![Repair approved and activated](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/kimmblo8u5yomp351knu.png)
*Figure 6: The repair is activated. The banner confirms: "APPROVED: Repair was activated. New runs now process with the repaired recipe."*

---

### 4. Quarantined File Re-executes Green (Zero Model Calls)
With Recipe v2 active, the quarantined file re-runs deterministically:

![Run history and Run 5 succeeded](https://dev-to-uploads.s3.us-east-2.amazonaws.com/uploads/articles/h3tc37ph7n0vfbzt9e8h.png)
*Figure 7: Run 5 succeeds under Recipe v2. Six rows written atomically, latency ~16ms, and exactly 0 runtime model calls.*

* **Timeline Update:** Run 5 turns **green** (`PASS: SUCCEEDED`).
* **Execution Metrics:** 6 rows processed, latency 16ms, **0 runtime LLM calls**.
* **Calls Avoided Chart:** The graph updates in real time, recording that steady-state production remains completely free of repeated model inference.

An LLM participated in fixing the pipeline. **An LLM never touched the data.**

---

## How I Built It: Where the Local Model Actually Failed

I tested `gemma3:4b` on a difficulty ladder, five trials per rung, because "it worked on my demo" is not engineering evidence.

| Task Difficulty | First Request Pass Rate | With Configured Retries | Verification Result |
| :--- | :---: | :---: | :--- |
| **Trim merchant text** | 5/5 | 5/5 | Verified & Passed |
| **Trim + parse dates** | 4/5 | 5/5 | Verified & Passed |
| **Trim + dates + decimals** | 3/5 | 4/5 | Verified & Passed |
| **Full 6-operation task** | **0/5** | **0/5** | **Blocked by Verifier** |

**Zero out of five.** On the full task—renames, regex split, date normalisation, currency parsing, category mapping, dedupe—a 4B model running on a laptop simply could not hold all six rules in context at once.

The failure mode is the one that should frighten you: in one run, Gemma's natural-language summary confidently stated that it had parsed the amount column. Its actual executable JSON omitted the decimal transform entirely. **The model told me it did something it had not done.**

In an ungated agent pipeline, that recipe ships and your amounts remain text strings. In Molt, the verifier rejected it, and **not one invalid recipe ever reached production across the whole ladder**. The architecture absorbed the model's weakness instead of inheriting it.

```json
// From evidence/gemma-rung3-rejected-candidate.json:
{
  "recipe": {
    "name": "Trim, Normalize Date, Parse Decimal",
    "description": "Trims whitespace from merchant, normalizes date to YYYY-MM-DD, and parses amount to two decimal places.",
    "operations": [
      {
        "type": "trim",
        "columns": [
          "merchant"
        ]
      }
    ]
  },
  "rung": 3,
  "verification": {
    "status": "FAIL",
    "failed_checks": 1,
    "failed_check_codes": [
      "golden_output"
    ]
  }
}
```
*Look at the operations array: it contains ONLY `trim`. The model claimed it parsed date and amount in its natural-language description, but completely omitted those operations from the executable JSON. Molt's verifier caught the discrepancy immediately and failed the golden check before anything could execute.*

That's the result I'm proudest of, and it only exists because I assumed from line one that the model would lie to me.

Evidence: [Full evaluation evidence](https://github.com/Pritam-mb/week3/blob/main/evidence/gemma-full-task-followup.json) · [Rejected candidate](https://github.com/Pritam-mb/week3/blob/main/evidence/gemma-rung3-rejected-candidate.json)

---

## But Is the Verifier Any Good? Mutation Testing

A verifier that never catches anything is just ceremony. So I mutated 20 known-good recipes on purpose—inverted dedupe keys, dropped transforms, unmapped categories—and measured what survived.

The initial suite caught **18 of 20**.

The two survivors were real gaps: an unmapped category policy and a dedupe key edge case. I wrote two targeted fixtures, re-ran the identical 20 mutations, and got **20/20 (100% catch rate)**, with the valid recipe still passing 11/11 checks cleanly.

```json
// From evidence/verifier-catch-rate-after.json:
{
  "before_summary": {
    "total": 20,
    "caught": 18,
    "missed": 2,
    "misses": [
      "dedupe_wrong_column",
      "preserve_unknown_policy"
    ],
    "catch_rate": 0.90
  },
  "after_summary": {
    "total": 20,
    "caught": 20,
    "missed": 0,
    "catch_rate": 1.00
  },
  "correct_recipe": {
    "verification_status": "PASS",
    "checks_passed": "11/11",
    "checks_failed": 0
  }
}
```

Evidence: [Mutation test evidence](https://github.com/Pritam-mb/week3/blob/main/evidence/verifier-catch-rate-after.json)

---

## Why Open Innovation Mattered Here

This project is only possible with open weights and open frameworks, and not for ideological reasons:

1. **The data can't leave:** Expense lines, payroll, invoice detail—these don't get posted to a third-party cloud API because a blog post said agents are cool. Gemma runs locally with zero network egress. The privacy boundary isn't a policy promise in a Terms of Service; it's the physical fact that the process makes no network calls.
2. **I could measure the model's limits:** Running locally and unmetered, I ran the ladder 20+ times, watched it fail, and designed the verifier around the observed failures. With a metered closed API I'd have run it three times, seen it mostly work, and shipped the silent-corruption bug.
3. **The artifact is readable:** An open model compiling to declarative JSON gives me something I can diff, review, commit to Git, and regression-test. A closed agent gives me a vibe and an invoice.
4. **It's swappable:** Gemma is a dependency, not a foundation. The allowlist and the verifier are mine. A better 4B model next month is a single config change, and the fact that it's a config change is itself the argument.
5. **Marginal cost is genuinely zero:** The recurring chore has no recurring bill.

---

## What Molt Can't Do (Explicit Limitations)

Being straight about this, because the post would be dishonest otherwise:

* **Verification is evidence, not mathematical proof:** My fixtures cover the input classes I imagined; a sufficiently novel or malicious file can still slip through a passing suite.
* **The op allowlist is deliberately narrow:** Anything outside those nine operations needs new code, not a new prompt.
* **A 4B local model cannot compile a six-rule recipe in one shot:** Complex chores need either a larger local model (e.g. 14B/32B) or decomposition into staged sub-recipes.
* **TabPFN is strictly advisory:** Evaluated on synthetic data, it flags statistical outliers but has no authority to alter records or block execution.
* **Molt is not autonomous by design:** A human promotes every recipe version. That is a deliberate ceiling on how lazy it will ever let you be.

---

## Demo: Try It in 30 Seconds

No API key, no Ollama install, and no network connection required.

### 1. Instant Offline Demo
```bash
python -m molt demo --offline --approve
```
*Four benchmark cases: two clean batches processed, two drifted batches halted, zero execution model calls.*

### 2. Live Local Dashboard
```bash
python -m molt --state-dir workspace serve --host 127.0.0.1 --port 8765
```
Open `http://127.0.0.1:8765/` in your browser.

![Molt Dashboard at 390px Mobile Resolution](https://raw.githubusercontent.com/Pritam-mb/week3/main/evidence/final-390.png)
*Figure 8: Responsive bento layout check at 390px width with 0px horizontal overflow.*

---

## Code: Under the Hood

Repository: **[https://github.com/Pritam-mb/week3](https://github.com/Pritam-mb/week3)**

The contract gate is the heart of the safety model, and it is forty lines of boring Python rather than anything clever:

```python
def check_contract(recipe: dict[str, Any], headers: list[str]) -> None:
    required = recipe["input_contract"]["required_columns"]
    missing = [c for c in required if c not in headers]
    if missing:
        raise MoltError(
            "REQUIRED_COLUMN_MISSING",
            f"Missing required column(s): {', '.join(missing)}.",
            details={"missing": missing, "expected": required, "observed": headers},
        )
    if recipe["input_contract"].get("allow_extra_columns") is False:
        extras = [c for c in headers if c not in required]
        if extras:
            raise MoltError(
                "INPUT_TYPE_MISMATCH",
                f"Unexpected column(s): {', '.join(extras)}.",
            )
```

Around it:
* [`molt/core.py`](https://github.com/Pritam-mb/week3/blob/main/molt/core.py): The deterministic execution engine, checkpoint ledger, and atomic writes.
* [`molt/application.py`](https://github.com/Pritam-mb/week3/blob/main/molt/application.py): Lifecycle state machine, verification gates, and human approval boundaries.
* [`molt/ollama.py`](https://github.com/Pritam-mb/week3/blob/main/molt/ollama.py): Constrained local Gemma/Ollama recipe compilation client.
* [`molt/temporal.py`](https://github.com/Pritam-mb/week3/blob/main/molt/temporal.py): Durable Temporal workflow definitions and activity worker.
* [`mastra-repair/`](https://github.com/Pritam-mb/week3/tree/main/mastra-repair): Isolated TypeScript microservice for out-of-band repair proposals.
* [`molt/web/`](https://github.com/Pritam-mb/week3/tree/main/molt/web): Obsidian graphite bento dashboard with zero external CDN dependencies.
* `tests/`: 79 Python unit/integration tests and 9 Node.js dashboard/diff tests.

---

### Three Integrations With Full In-Post JSON Evidence

Rather than asking you to blindly trust marketing claims, here is the exact machine-verified evidence for our partner integrations:

#### 1. Temporal: Crash Recovery & Durable Checkpointing
Steady-state execution runs inside a durable Temporal workflow. We injected process kills mid-flight (`MOLT_CRASH_AT=1` killing both worker and server). Upon restart, Temporal picked up from step 1's saved checkpoint without duplicate writes and without making any model calls:

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
  },
  "claim_boundary": "Real local Temporal server and worker workflow; one injected activity failure and idempotent retry."
}
```

#### 2. TabPFN: Local Advisory Anomaly Detection
Evaluated locally on CPU across 1,500 synthetic expense rows (1,200 training rows, 300 held-out test rows). It flags statistical schema spikes without modifying a single byte of source data:

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
*Why is 72% recall acceptable?* Because TabPFN is strictly advisory and non-blocking—it is an extra signal for operator triage, while the deterministic Python contract gate is what actually guarantees zero corrupt rows reach disk.

#### 3. Sentry: 9-Stage Distributed Tracing & Strict Redaction Allowlist
Molt instruments all **nine workflow lifecycle stages** in [`molt/application.py`](https://github.com/Pritam-mb/week3/blob/main/molt/application.py) using an allowlist-based scrub boundary in [`molt/telemetry.py`](https://github.com/Pritam-mb/week3/blob/main/molt/telemetry.py):

```text
The 9 Lifecycle Tracing Spans:
1. automation.profile_csv        (profiles header names and inferred dtypes)
2. tabpfn.score_rows             (computes advisory outlier probabilities)
3. recipe.validate_operations    (enforces closed 9-op allowlist)
4. recipe.compile_gemma          (local Ollama compiler envelope check)
5. recipe.verify_examples        (runs golden fixture regression tests)
6. recipe.approve_version        (records explicit operator promotion)
7. repair.propose                (dispatches masked schema to Mastra sidecar)
8. automation.check_drift        (pure Python contract check in 16ms)
9. automation.execute_approved_recipe (deterministic Python transform)
```

**The Redaction Proof (Why It Is Safe to Upload):** To guarantee that confidential payroll data, invoices, customer PII, or internal file paths never leave your infrastructure, `molt/telemetry.py` enforces a strict two-tier scrub boundary:

1. **Strict Key Allowlist:** Attributes are dropped by default unless explicitly included in the safe set:
```python
# From molt/telemetry.py:
_SAFE_ATTRIBUTE_KEYS = {
    "attempt", "checks_passed", "checks_total", "column_count",
    "input_bytes", "input_rows", "model_calls", "output_rows", "status"
}
_SENSITIVE_KEY_PARTS = (
    "content", "csv", "file", "path", "prompt", "response", "row", "secret", "token", "value"
)
```

2. **Payload Scrub Hook:** The Sentry SDK initializes with `send_default_pii=False` and hooks `before_send` and `before_send_transaction` to sanitize payloads before transmission:
```python
# Verified in tests/test_telemetry.py:
scrubbed = before_send({
    "message": "raw",
    "request": {"url": "https://private/path"},
    "status": "ok",
    "count": 3,
    "data": {
        "prompt": "raw prompt",
        "input_rows": 4,
        "free_text": "raw csv cell value: $1,240.00"
    }
})
# Result verified by unit test:
assert scrubbed == {"status": "ok", "count": 3, "data": {"input_rows": 4}}
```
![Sentry 9-Stage Distributed Trace Waterfall](https://raw.githubusercontent.com/Pritam-mb/week3/main/evidence/sentry-trace.png)
*Figure 9: Real live Sentry waterfall trace for molt showing all 9 lifecycle stages executing deterministically in ~50ms with zero customer row content.*

*Privacy in Practice:* As shown in the trace waterfall above, every stage executes with zero raw row payloads, zero financial numbers, and zero PII. The Sentry dashboard reflects only stage names, millisecond durations (~5ms per span, 50.96ms total root duration), and aggregate status metrics. When `SENTRY_DSN` is empty, Molt defaults to 100% offline mode (`mode: local-only`).

---

## Verification Snapshot

Recorded October 25, 2026:

| Check | Result | Details |
| :--- | :---: | :--- |
| **Python test suite** | **79 PASSED, 20 subtests** | Full core, app, and verifier suite |
| **Dashboard & diff (Node)** | **9 PASSED** | Web UI lifecycle & diff integrity |
| **Mastra TypeScript build** | **PASSED** | Clean `tsc --noEmit` |
| **Gemma local smoke compile** | **PASSED** | Passed all envelope, schema & profile gates |
| **Mastra live repair** | **PASSED** | 6/6 verifier checks passed |
| **Temporal chaos recovery** | **PASSED** | Checkpoint resume, no duplicate writes |
| **TabPFN evaluation** | **PASSED** | 94.55% precision, full matrix disclosed |
| **Sentry redaction** | **PASSED** | Strict allowlist verified |
| **Offline submission check** | **PASSED** | 0 model calls, clean execution + quarantine |
| **Drift benchmark** | **PASSED** | 0 silent errors vs. 3 naive script errors |

### Machine-Readable Verification Evidence

Here is the exact verification check recorded from [`evidence/live-integration-check-2026-10-25.json`](https://github.com/Pritam-mb/week3/blob/main/evidence/live-integration-check-2026-10-25.json):

```json
{
  "checked_at": "2026-10-25",
  "privacy": "Aggregate-only evidence. Zero raw row payloads recorded.",
  "repository_checks": {
    "python_pytest": "79 passed, 20 subtests passed",
    "node_dashboard_and_diff": "9 passed",
    "typescript_build": "PASS",
    "offline_submission_check": "PASS",
    "benchmark": "PASS"
  },
  "gemma_ollama": {
    "status": "PASS",
    "model": "gemma3:4b",
    "live_model_calls": 1,
    "validation_gate": {
      "response_envelope": "PASS",
      "recipe_schema": "PASS",
      "profile_contract": "PASS"
    }
  },
  "mastra_groq": {
    "sidecar_health": "PASS",
    "provider_model": "groq/openai/gpt-oss-120b",
    "model_calls": 1,
    "molt_verification": "PASS",
    "verification_checks": "6/6",
    "human_approval": "gated"
  },
  "tabpfn": { "precision": 0.9455, "recall": 0.7222, "source_bytes_altered": 0 },
  "temporal": { "status": "PASS", "checkpoint_recovery": "idempotent", "model_calls": 0 }
}
```

---

## Prize Categories

* **Best Use of Gemma:** Local `gemma3:4b` compilation, constrained JSON schema output, a published failure ladder including an honest 0/5 result, and zero-call reuse thereafter.
* **Mastra Agent Sidecar:** Out-of-band TypeScript repair agent with typed read-only tools and masked schema profiles, gated behind Molt’s own verifier and human approval.
* **Best Use of Temporal:** Durable steady-state execution with injected crash recovery (`MOLT_CRASH_AT=1`), checkpoint barriers, and idempotent replay.
* **Best Use of TabPFN:** Local CPU anomaly advisory with a fully disclosed confusion matrix, non-commercial licensing boundaries, and zero data modification.
* **Sentry:** Nine-phase tracing with strict allowlist redaction stripping all row values and PII.

---

The point of Molt isn’t that the AI is right. On the hardest task I gave it, it was wrong five times out of five and told me it had succeeded.

**The point is that it never gets the last word.**

#devchallenge #hf26challenge #ai #opensource
