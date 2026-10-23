# Molt: compile once, verify it, reuse it without repeated inference

Most CSV automation demos stop at “the model generated some code.” Molt uses
a stricter lifecycle: a local Gemma model proposes a constrained JSON recipe,
independent fixtures decide whether it is correct, a human approves it, and
compatible files then run deterministically without another model call.

The proof is a small live task. Gemma proposed a merchant-trimming recipe,
the independent verification suite passed it 6/6, and the approved reuse run
succeeded with `llm_calls=0`. When a required column drifted, Molt blocked the
run and quarantined the input. A repair candidate also had to pass its full
regression suite before approval.

The model is local through Ollama (`gemma3:4b`). The artifact is readable JSON,
not arbitrary generated Python or shell. The deterministic runtime is
separate from the model, so the model can be swapped without changing the
execution semantics.

## What happened when the task got harder?

I measured a fixed task ladder with five attempts per rung:

| Task | Pass@1 | Pass within configured retries | Outcome |
|---|---:|---:|---|
| Trim merchant | 5/5 | 5/5 | Passed |
| Trim + normalize dates | 4/5 | 5/5 | One retry recovered |
| Trim + dates + decimals | 3/5 | 4/5 | One exhausted rejection |
| Full expense task | 0/5 | 0/5 | Five provider timeouts |

The full-task failure is not hidden. It is exactly why Molt verifies before
approval: a candidate that adds an operation nobody requested remains rejected,
and a timeout does not become an active recipe.

## Drift benchmark

Using fixed seed 41 and an independently authored naive positional script:

- the naive baseline produced 3 silent wrong outputs across four drift cases;
- it accepted 2 cases that Molt classified as required-column drift;
- Molt blocked 2 cases and quarantined 2 files;
- reordered and extra-column cases were accepted by Molt because the contract
  is column-name based and preserves unrelated columns.

This is a behavior comparison, not an electricity-savings measurement. Cost is
not estimated because no provider price or script-maintenance price was
invented.

## Why open/local matters

The CSV and recipe stay in the local workspace during the demonstrated flow.
The recipe is inspectable. The model boundary is replaceable. The approval and
verification evidence are stored in SQLite rather than hidden in a chat log.

## Limits

Fixtures can be weak. A wrong-but-passing recipe is still possible if the
expected outputs do not cover the important behavior, and a human can approve
carelessly. The verifier catch-rate experiment caught 18 of 20 deliberately
wrong recipes on the current fixture set; it missed a dedupe-key mutation that
happened to be equivalent on the fixture and a preserve-unknown policy that was
not exercised by those fixtures.

TabPFN completed a live supervised advisory run on a synthetic labeled fixture:
300 held-out rows were scored and 55 were flagged, with the source preserved
and zero rows changed. This is not unlabeled anomaly detection or real-world
drift validation. Temporal also completed one live workflow around an approved
fixture recipe; that proves the durable execution boundary, not live Gemma
generation. The full expense Gemma rung is still not claimed as successful.

Evidence files for every number are in `evidence/`, especially
`gemma-ladder.csv`, `benchmark.json`, `lifecycle.json`, and
`verifier-catch-rate.json`.

#devchallenge #hf26challenge
