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

The repository currently has a Threadwork dashboard: a task is shown as a
thread, steps are beads, a live run sends a small bead along the line, and drift
cuts the run lane instead of silently continuing. [Pipeline illustration](evidence/pipeline.png)

<!-- ATTACHMENT SLOT: live Threadwork dashboard screenshot, only if fully sanitized. -->

## How the boundary works

```text
profile input
    -> Gemma proposes constrained JSON
    -> schema validation
    -> fixture outputs and invariants
    -> explicit approval
    -> deterministic execution, zero model calls
    -> drift? block + quarantine
    -> repair candidate
    -> same verification suite + explicit approval
```

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

## When the data changes

The live lifecycle is the part I wanted the model to support without allowing it
to become the final authority:

1. A `gemma3:4b` candidate was created.
2. The candidate passed 6/6 checks.
3. A scripted approval activated it.
4. A compatible four-row input ran with zero model calls.
5. A drifted input was blocked with `REQUIRED_COLUMN_MISSING`.
6. No rows were written and quarantine was observed.
7. A repair candidate failed a 6-check verification and stayed rejected.
8. A separate repair candidate passed 8/8 checks and was explicitly approved.

The drift block, rejected repair and approved repair are recorded lifecycle
events. They are not one continuous live Gemma repair video. A successful live
Gemma-generated repair is not shown. [Lifecycle record](evidence/lifecycle.json)

<!-- ATTACHMENT SLOT: sanitized live dashboard screenshot, if one exists. -->

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
- **Best Use of Temporal:** narrow live workflow claim only: checked-in fixture
  recipe, four-row input, three output rows and zero model calls.
- **Best Use of TabPFN:** synthetic supervised advisory evaluation with the full
  confusion matrix and limitations stated.
- **Sentry:** tracing is implemented, but I am not claiming a clean trace or
  submitting a dashboard screenshot.

The point of Molt is not that the model is always right. It is that the model
does not get the last word.

#devchallenge #hf26challenge #ai #opensource
