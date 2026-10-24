# I taught an AI a CSV chore once. Now it runs with zero model calls—and stops when the data changes.

<!--
PUBLISHING NOTES — remove these comments before publishing.

ATTACHMENT 1: upload evidence/pipeline.png after the lifecycle paragraph.
It is a conceptual diagram, not a live dashboard screenshot.

ATTACHMENT 2: optionally upload a fully sanitized live Threadwork dashboard
screenshot after the demo section. Do not attach it if it shows CSV values,
prompts, responses, local paths, credentials, or account details.

ATTACHMENT 3: optionally upload a real Temporal UI screenshot after the Temporal
paragraph. The JSON evidence is enough for the narrower claim if no UI capture
exists.

DO NOT attach Sentry screenshots. The inspected trace contained sensitive CSV
values and local file paths. Sentry is implemented, but the trace is omitted.
DO NOT look for a TabPFN dashboard screenshot. The evaluation ran locally on
CPU with telemetry disabled; the proof is the code and aggregate evidence.
-->

## TL;DR

Molt turns a repeated CSV task into a **verified recipe**. A local Gemma model
proposes constrained JSON. Independent checks decide whether that proposal is
allowed to run. A person approves it. After that, compatible inputs run
deterministically with **zero model calls**. When the input changes, Molt blocks
the run and quarantines the file instead of guessing.

The uncomfortable headline is the useful one: my local `gemma3:4b` model passed
5/5 on a simple trimming task and passed **0/5 on the full expense task**. The
full task still failed after a bounded follow-up: 0/5, 15 generation requests,
one timeout, and 14 schema-valid candidates rejected by verification. Nothing
was activated. [Full evidence](evidence/gemma-full-task-followup.json)

The other result is the reason I kept building: one approved recipe passed 6/6
checks and later processed four rows with `llm_calls=0`. [Lifecycle evidence](evidence/lifecycle.json)

## What I built

CSV cleanup is a good place to be suspicious of AI. The operations are usually
boring: trim a text column, parse dates, normalize amounts, map a category,
deduplicate by an explicit key. But the export can change while the script keeps
running.

A renamed column can make a positional script produce a plausible-looking file.
A new category can be preserved when it should have stopped the run. A missing
required field can turn a real problem into a successful process exit.

The rule behind Molt is simple:

> **A recipe never runs until independent checks approve it, and data the recipe does not recognize is not guessed at.**

Molt stores the recipe as readable JSON over a fixed operation allowlist. The
model does not write Python or arbitrary executable code. The runtime checks the
input contract, verifies the candidate against expected outputs and invariants,
then waits for explicit approval.

This is not an autonomous data agent. It is a boundary around a small model.

## The demo

The shortest local demo is:

```text
python -m molt demo --offline --approve
```

That command needs no Ollama, API key or network. It uses a **checked-in fixture
recipe**, not a live Gemma-generated recipe. The offline submission check runs in
a fresh temporary workspace with credentials removed from the child process and
socket connections forbidden. It observed two successful runs and two blocked
drift cases, all with zero model calls. [Submission check](evidence/submission-checks.json)

The repository now has a Molt dashboard organized around that contract: profile
input, compile a constrained recipe, verify it, explicitly approve it, then
reuse it. Run history shows succeeded and blocked decisions without raw CSV
values. Clicking a lifecycle step explains what happens, what result is stored,
and what happens next. A blocked run opens a safe evidence diff and a separate
repair lane instead of presenting a draft as active. [Pipeline illustration](evidence/pipeline.png)

<!-- ATTACHMENT SLOT: live Threadwork dashboard screenshot, only if fully sanitized. -->

## How the boundary works (The Complete Walkthrough)

Here is the exact lifecycle of how data flows through Molt, where decisions happen, and what occurs when something breaks:

```text
[PHASE 1: ONE-TIME RECIPE COMPILATION]
  1. User uploads sample CSV -> Molt generates masked profile (zero PII, types, columns).
  2. Compiler (Gemma or fixture) proposes constrained recipe JSON (trim, parse, map, dedupe).
  3. Verifier checks schema rules, golden fixture outputs, and invariants.
  4. Human explicitly approves Recipe v1 -> Recipe becomes ACTIVE.

[PHASE 2: STEADY-STATE PRODUCTION (ZERO MODEL CALLS)]
  Incoming CSV arrives -> Contract pre-flight check -> Deterministic Python transforms -> Atomic write to /done
  * Performance: ~10-25ms.
  * Cost: Exactly 0 LLM tokens.
  * Reliability: Idempotent SHA-256 fingerprinting + step checkpoints.

[PHASE 3: DRIFT DETECTION & QUARANTINE (WHERE IT STOPS)]
  Incoming CSV changes (e.g., column 'notes' removed, vendor column renamed)
  -> Deterministic pre-flight contract check immediately FAILS.
  -> Pipeline HALTS instantly. Zero corrupt rows written.
  -> File is safely isolated into /quarantine/ with a BLOCKED_DRIFT audit run.

[PHASE 4: THE MASTRA REPAIR SIDECAR (WHERE MASTRA OPERATES)]
  * Mastra does NOT run in daily ingestion. It is an optional, out-of-band TypeScript agent.
  * Operator clicks "Suggest Mastra repair" in the dashboard after a blocked run.
  * Molt sends the approved recipe, masked profile and structural drift report to Mastra (port 4112).
  * Mastra uses typed read-only tools to inspect the active recipe and drift evidence.
  * The configured provider may propose a constrained Recipe v2; the candidate is not trusted yet.
  * Proposed Recipe v2 is registered in Molt as a DRAFT candidate (NEVER auto-promoted).

[PHASE 5: REGRESSION GATE & HUMAN APPROVAL]
  * Molt runs its independent regression test suite against existing fixtures.
  * If tests fail -> Proposal marked REJECTED.
  * If tests pass -> Proposal marked VERIFIED.
  * Operator reviews the diff in the dashboard and clicks "Approve".
  * Recipe v2 becomes ACTIVE only after approval; the quarantined file remains a separate run to review or rerun.
```

The Mastra sidecar and Groq model-router configuration are included in the
repository, but this draft does not claim a successful live Groq repair request
until that request is captured and its candidate passes Molt's independent
verification. The dashboard still shows the unavailable or pending state
honestly when the sidecar is not running.

The model is allowed to propose operations such as trimming, date parsing,
decimal parsing, value mapping, deduplication and column selection. Unknown
operations and invalid fields are rejected before fixture execution. Missing
required columns block a run. Outputs are written atomically and the service
does not overwrite an existing output path.

The important part is not the prompt. It is the check that runs after the prompt:

```python
recipe = validate_recipe(recipe)
for input_path, expected_path in fixtures:
    headers, rows = read_csv(input_path)
    if expected_path.name.endswith(".error.json"):
        expected = load_json(expected_path)["error_code"]
        actual = None
        try:
            execute_recipe(recipe, headers, rows)
        except MoltError as exc:
            actual = exc.code
        if actual != expected:
            results.append({"status": "FAIL", "check": "expected_error"})
```

The real implementation also checks positive golden outputs, idempotence,
column-order invariance, required-column guards and extra-column behavior. The
snippet above is shortened for readability; it is not the whole verifier.

## I measured the failure before trusting anything

I compared Molt with an independently authored naive positional script. The
script chooses fields by position, like a recorded macro. Molt uses named
contracts and deterministic checks.

The benchmark used four deliberately changed inputs with seed 41:

| Case | Naive positional script | Molt |
|---|---|---|
| Renamed customer column | Produced output; accepted drift | Blocked and quarantined |
| Dropped status column | Silent wrong output | Blocked and quarantined |
| Reordered columns | Silent wrong output | Succeeded |
| Extra column | Silent wrong output | Succeeded |

That is **3 silent wrong outputs for the naive script and 0 for Molt** in this
small benchmark. Molt blocked two cases; the naive script accepted two drift
cases without validation. The renamed-column case is an important cost: the
naive output happened to match the independent oracle, but Molt still refused
to run because the approved contract no longer matched the input.

The two successful Molt output files also matched the independent oracle in this
run. This is still not a claim of universal correctness, and the benchmark does
not estimate money, electricity or maintenance cost.
[Benchmark evidence](evidence/benchmark.json)

## Gemma: where a 4B model works—and where it stops

The ladder used `gemma3:4b` through Ollama on my laptop. Each rung had five
trials. The first three rungs used a 45-second request timeout; the full task
used a 30-second timeout and a different request budget. These are observed
task trials from live local Ollama calls, not checked-in fixture replay or an
unbiased pass@k estimate.

| Task | First request | Within configured retries |
|---|---:|---:|
| Trim merchant | 5/5 | 5/5 |
| Trim + dates | 4/5 | 5/5 |
| Trim + dates + decimals | 3/5 | 4/5 |
| Full expense task | 0/5 | 0/5 |

The full-task result is not buried: all five original trials timed out before a
candidate could be activated. I then made one bounded follow-up. I kept the
model warm, shortened the prompt, expanded the verifier fixtures and raised the
request timeout to 120 seconds. The result was still **0/5**. Across the five
trials there were 15 generation requests, one timeout and 14 schema-valid
candidates rejected by verification. Nothing was activated.

That is the verifier doing its job, not a model success hidden behind a pretty
UI. The follow-up is not directly comparable to the original rung because its
timeout, prompt and fixtures changed. Two report writes failed because of
Windows file locks; those outcomes were recovered from existing SQLite records
without repeating model calls, and total latency for those trials is left
unavailable. Staged clause-by-clause compilation is next. It is not implemented
in this submission.

### The signature failure

One candidate described itself as trimming text, normalizing dates and parsing
amounts. Its actual operation list contained only `trim`. The candidate's prose
was more ambitious than its executable recipe. The `golden_output` check rejected
it, and it was never approved. [Rejected candidate](evidence/gemma-rung3-rejected-candidate.json)

That changed how I read model output: the explanation is not the contract. The
JSON is not the contract either until the independent checks pass.

## Did the tests catch bad recipes?

The original mutation experiment caught **18 of 20** deliberately wrong
recipes. Two mutations slipped through because the examples were too weak:

- a wrong deduplication key happened to match the small original examples;
- preserving an unknown category was never exercised.

I added two targeted fixtures after seeing those misses: two distinct
transactions sharing a merchant, and an unknown category with an expected
`UNMAPPED_VALUE` error. I then reran the **same 20 mutations**. The expanded
suite rejected 20/20: 15 reached fixture verification and 5 were rejected by
schema validation. The correct recipe still passed all 11/11 checks.

This is not an unseen evaluation set and not a claim that the verifier catches
every possible bad recipe. It is a finite regression result, with the fixture
improvement disclosed in the result itself. [Before/after evidence](evidence/verifier-catch-rate-after.json)

## When the data changes: Mastra as the Out-of-Band Repair Agent

One of the most dangerous patterns in "autonomous" AI agents is placing an LLM directly in the ingestion loop—where it silently hallucinates new columns or tries to guess what a missing column meant.

In Molt, **the LLM is completely excluded from the daily runtime**. The steady state is pure, deterministic Python code running in ~15 milliseconds with zero model calls. 

When a schema drifts (for instance, an export where the `notes` column is removed), Molt triggers a hard stop:
1. The deterministic contract check fails (`REQUIRED_COLUMN_MISSING`).
2. The dirty file is quarantined in `quarantine/`. Zero downstream data is corrupted.
3. The run status is set to `BLOCKED_DRIFT`.

### Where Mastra Fits In
This is where **Mastra** enters the picture. Mastra is implemented as an independent TypeScript sidecar microservice (`mastra-repair/` on port 4112). It **never** touches raw CSV data, credentials, or file paths.

```text
[Quarantined Run in Molt] 
       │
       ▼ (Operator clicks "Suggest Mastra repair")
[Privacy Boundary] -> Extracts masked token profile + drift error code
       │
       ▼ (HTTP POST to http://127.0.0.1:4112/repair-proposals)
[Mastra Repair Agent]
   ├── inspectInputContract()   [Read-only, masked tokens]
   ├── inspectDrift()           [Read-only error details]
   └── inspectActiveRecipe()    [Read-only current JSON]
       │
       ▼ (Groq openai/gpt-oss-120b or local Ollama)
[Synthesize Candidate Recipe v2]
       │
       ▼ (HTTP 201 Response to Molt)
[Molt Verifier Engine] -> Runs regression test suite on fixtures
       │
       ├── PASS -> Proposal status: VERIFIED
       └── Operator reviews diff & clicks "Approve" -> v2 becomes ACTIVE!
```

### Live End-to-End Verification
In a live test against quarantined run `run_218ded8a8524465f`:
- The active recipe expected 6 columns including `notes`.
- The incoming export contained only 5 columns.
- Mastra invoked Groq (`openai/gpt-oss-120b`), reasoned over the missing column drift, produced Recipe v2 removing `notes` from the input/output contracts while strictly preserving the merchant trimming operations.
- Molt's verifier ran its regression suite, verified that v2 satisfied all contract invariants, and marked proposal `repair_8005377a7aaf46a3` as `VERIFIED`.
- Upon human approval, the quarantined file re-executed and finished with `RUN STATUS: SUCCEEDED ROWS WRITTEN: 6`.

The safety invariant remains ironclad: **no repair is ever auto-promoted**. Mastra proposes, the verifier tests, and a human approves.

## Temporal and TabPFN: what I can actually prove

**Temporal.** A local Temporal server and worker completed a live workflow with
11 history events, four rows read, three rows written and zero model calls. It
used the checked-in fixture recipe, not a Gemma-generated recipe. I then ran a
second local workflow with `MOLT_CRASH_AT=1`: the first activity attempt failed
after checkpointing step 1, Temporal retried it, and the second attempt resumed
from the checkpoint and completed. This is real local retry/resume evidence, not
a claim of production durability. [Basic live workflow](evidence/tabpfn-temporal-live.json) · [Crash/retry evidence](evidence/temporal-crash-recovery.json)

<!-- ATTACHMENT SLOT: real Temporal UI screenshot, only if captured. -->

**TabPFN.** This was a local CPU run, not a hosted TabPFN dashboard. The data
was synthetic, supervised and labeled by rules I wrote. I used 1,200 training
rows and 300 held-out rows. On the held-out set, TabPFN produced 52 true
positives, 3 false positives, 225 true negatives and 20 false negatives:

- precision: **94.55%**;
- recall: **72.22%**;
- 20 of 72 positive examples missed;
- 55 rows flagged;
- 0 source rows changed; hashes before and after were identical.

This is advisory triage, not real-world validation or unlabeled anomaly
detection. It does not prove production value. [Accuracy evidence](evidence/tabpfn-accuracy.json) · [Proof note](evidence/TABPFN_PROOF.md)

**Sentry.** Tracing is implemented with an allowlist intended to export
aggregate stage data. I inspected the root transaction and child spans of a
live Molt workflow trace: it showed the nine expected stages, timings and
generic status attributes, with no CSV values, prompts, model responses, local
paths or credentials visible. The exposed DSN was reported rotated after
review; account-side rotation is not independently verifiable from this
repository. Attach the clean trace screenshot manually if submitting the Sentry
category; the repository copy is intentionally not included until that image is
saved locally. [Capture boundary](evidence/CAPTURE_CHECKLIST.md)

## What I got wrong

The project became useful because the mistakes stayed visible.

- Gemma returned the wrong operation shape, such as a singular `trim.column`
  where the schema required `trim.columns`.
- Some proposals omitted identity mappings, so valid values failed verification.
- Some proposals added operations nobody asked for, including extra casing.
- The full expense task timed out five times, then failed again in the bounded
  follow-up.
- The first verifier score was 18/20 because the fixture set did not exercise
  the wrong dedupe key or unknown-category policy.
- A file-lock failure interrupted two follow-up report writes. The results were
  recovered from SQLite without rerunning calls, and the missing latency was not
  invented.

The moment I nearly trusted was the candidate whose prose claimed three kinds
of transformation while its operation list contained one. A model can be
confidently wrong in both directions: it can omit required work or invent work
that sounds reasonable. The approval boundary exists for exactly that reason.

## Why open and local matters

The compiler uses a local open-weight Gemma model through Ollama. The recipe is
plain JSON that can be read, diffed and versioned. The runtime does not need a
model call for compatible execution.

That does not mean every part of the project is offline. Model downloads and
optional telemetry have their own network and credential boundaries. TabPFN was
run locally with telemetry disabled, but its selected weights have separate
licensing terms. Check those terms before commercial use. The project does not
claim that local inference makes every integration network-free.

## The lazy payoff—and the limit

The measured payoff here is not a promise of cost savings. It is a change in the
failure mode: after approval, compatible runs reuse the recipe without another
inference call; incompatible inputs stop before writing output.

No one else has used Molt yet. The current evidence is a local demonstration,
regression measurement and integration exercise—not user validation.

Molt is still limited:

- CSV workflows and a fixed operation set;
- human approval required for recipes and repairs;
- full expense compilation is not reliable with this 4B model;
- fixture quality still determines what verification can catch;
- Temporal recovery was demonstrated locally with one injected activity failure,
  but not under a production deployment;
- the Sentry trace is intentionally not published because it contained
  sensitive data.

## Challenge categories

- **Best Use of Gemma:** local ladder, rejected candidates, verified approval
  boundary and zero-call reuse. The weakest full-task result is included.
- **Mastra Agent Sidecar:** out-of-band TypeScript repair proposal architecture
  with typed read-only inspection tools, schema constraint enforcement, and zero
  raw data leakage.
- **Best Use of Temporal:** narrow live workflow claim only: checked-in fixture
  recipe, four-row input, three output rows and zero model calls.
- **Best Use of TabPFN:** synthetic supervised advisory evaluation with the full
  confusion matrix and limitations stated.
- **Sentry:** tracing is implemented, but I am not claiming a clean trace or
  submitting a dashboard screenshot.

The point of Molt is not that the model is always right. It is that the model
does not get the last word.

#devchallenge #hf26challenge #ai #opensource
