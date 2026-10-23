# Molt Gaps, Fixes, and Submission Notes

## Current status

### Submission audit superseding earlier status below

- `POST_DRAFT.md` now distinguishes scripted approval from independent human
  review; fixture drift/repair and the live trim run are separate evidence.
- Exact original mutation edits were recovered from the earlier inline session
  command. `verifier_measurement.py` reproduces 18/20 on old fixtures and 20/20
  after adding a distinguishing dedupe fixture and an expected-error oracle.
  Five rejections are schema errors, not semantic fixture catches.
- TabPFN real synthetic holdout: TP=52, FP=3, TN=225, FN=20; precision 94.55%,
  recall 72.22%. Source preserved by hash. See `evidence/tabpfn-accuracy.json`.
- Warm Gemma follow-up is complete: 0/5 passes, 15 requests, one timeout and 14
  verification-rejected candidates; no activation. Original ladder is unchanged.
  No staged compiler added. See `evidence/gemma-full-task-followup.json`.
- Temporal wording: live fixture recipe, four-row input, zero model calls;
  not Gemma generation or a demonstrated worker-crash recovery.
- Read-only history scan: `.env` not tracked; no matches for current token/DSN.
  Credential-shaped historical content in `workflow.txt` and an older
  `.env.example` needs private review/revocation if real. `workflow.txt` still
  contains a match. No history rewriting, publication, or credential rotation done.
- Capture gaps: dashboard screenshot, Temporal UI (server is headless), Sentry
  trace inspection and DSN rotation, external reader feedback, publishing preview.
  Details: `evidence/CAPTURE_CHECKLIST.md`.

### Earlier refinement status (historical)

- Tier A1: complete for four measured rungs. Rungs 1–3 produced real passing
  and rejection data. Rung 4 had five bounded `GEMMA_TIMEOUT` results; no full
  expense pass-rate claim is made.
- Tier A2: complete at the prompt/feedback level. The compiler now says to use
  only requested operations and never add casing or normalization merely
  because mapping is present. Verification feedback remains structural and
  redacted.
- Tier A3: complete for the current proof package under `evidence/`.
- Tier A4: complete in `bench.py` with an independently authored positional
  baseline, fixed seed 41, four drift cases, silent-wrong counts, and actual
  Molt block/quarantine counts.
- Tier A5: draft started in `POST_DRAFT.md`. Every reported number points to a
  saved artifact in `evidence/`.
- Tier B1: measured 20 deliberately wrong recipes. The verifier caught 18 and
  missed 2: deduping on `merchant` happened to produce the same result for the
  fixture, and `on_unmapped: preserve` was not exercised by the golden/held-out
  fixtures. The report is `evidence/verifier-catch-rate.json`.
- TabPFN live proof is complete on the synthetic labeled fixture; the sanitized
  result is `evidence/tabpfn-temporal-live.json`.
- Temporal live proof is complete with a local development server, worker, and
  approved fixture workflow. The worker now exposes an async activity wrapper
  and runs Molt's synchronous service in a thread, as required by the current
  Temporal Python SDK.

## Section 8 — Post draft outline

### Working title

**Molt: compile a repeated CSV task once, verify it, then reuse it without
calling the model again**

### Claim

Molt is a local-first lifecycle for repeated CSV work: a local Gemma model
proposes a constrained recipe, independent tests decide whether it is safe,
and a person approves it before compatible files run deterministically with
zero model calls. Schema drift blocks and quarantines inputs instead of
silently guessing.

### Proof sequence

1. A live local Gemma candidate for a small merchant-trimming task passed the
   independent fixture suite.
2. A human approved the candidate.
3. The approved reuse run succeeded with `llm_calls=0`.
4. A drifted input was blocked and quarantined.
5. A repair candidate passed the regression suite before approval.
6. A deliberately wrong Gemma candidate was retained as rejected evidence.
7. The fixed-seed benchmark showed the naive positional baseline producing 3
   silent wrong outputs while Molt blocked 2 required-column drift cases.

### Real Gemma ladder table

Use `evidence/gemma-ladder.csv` as the source of truth:

| Rung | Task | Pass@1 | Pass within configured retries | Result |
|---|---|---:|---:|---|
| 1 | Trim merchant | 5/5 | 5/5 | Passed |
| 2 | Trim + dates | 4/5 | 5/5 | Passed with one retry |
| 3 | Trim + dates + decimals | 3/5 | 4/5 | One exhausted rejection |
| 4 | Full expense task | 0/5 | 0/5 | Five provider timeouts |

The full expense rung is explicitly not presented as working live evidence.

### Why open/local matters

- The model boundary is local Ollama/Gemma.
- CSV data stays in the workspace during the demonstrated flow.
- The model emits readable JSON recipes, not arbitrary code.
- The deterministic runtime is inspectable and model-swappable.
- Verification and approval are separate from generation.

### Limits / not shown

The fixtures can only test the rules they encode; a wrong-but-passing recipe
or careless approval remains possible. TabPFN is live-demonstrated only as
supervised advisory triage on synthetic labels; it is not unlabeled anomaly
detection or real-world drift validation. Temporal is live-demonstrated with
the approved fixture recipe, not with live Gemma generation. The full expense
Gemma rung timed out and is not claimed as successful.
Sentry evidence is omitted unless its redacted trace is inspected directly.

### Post checklist

- [x] Replace any placeholder with a path in `evidence/`.
- [ ] Include one rejected candidate honestly.
- [ ] Keep `pass@1` and retry figures tied to the saved ladder file.
- [ ] Include the benchmark table and its fixed seed.
- [ ] Add tags `#devchallenge` and `#hf26challenge`.
- [ ] Read the post aloud and remove claims that are broader than the proof.

### Verifier catch-rate note

Do not write “the verifier catches every bad recipe.” The measured result is
18/20 intentionally wrong recipes caught on the current fixture set. The two
misses are useful limits: a wrong dedupe key can be observationally equivalent
on a small fixture, and a preserve-unknown policy needs an unknown-value
regression fixture to be tested.
