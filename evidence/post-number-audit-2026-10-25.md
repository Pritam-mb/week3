# Post number audit — October 25, 2026

The submission post uses the following measured values. Each value below is
checked against the named evidence file; no number is presented as a universal
correctness claim.

| Post claim | Evidence | Value checked |
|---|---|---|
| Benchmark used four changed inputs with seed 41 | `benchmark.json` | 4 cases, seed 41 |
| Naive positional baseline | `benchmark.json` | 3 silent wrong outputs, 2 accepted drift cases |
| Molt benchmark result | `benchmark.json` | 2 blocked, 2 succeeded, 2/2 successful oracle matches |
| Offline demo | `submission-checks.json` | 2 succeeded, 2 blocked, 0 execution model calls |
| Gemma ladder | `gemma-ladder.csv` and rung JSON | 5/5, 4/5, 3/5, 0/5 initial results; 5/5, 5/5, 4/5, 0/5 within retries |
| Full-task follow-up | `gemma-full-task-followup.json` | 0/5, 15 generation requests, 1 timeout, 14 rejected candidates |
| Verifier before/after | `verifier-catch-rate-after.json` and `verifier-final-guardrails.json` | 18/20 before, 20/20 after, correct recipe 11/11 |
| Live Mastra/Groq check | `live-integration-check-2026-10-25.json` | 1 model call, candidate verified 6/6, human approval not performed |
| Temporal chaos check | `temporal-chaos.json` | 2 worker kills, 1 server kill, 2 successful outputs, 1 drift block, 1 replay, 0 model calls |
| TabPFN holdout | `tabpfn-accuracy.json` | 1,200 train, 300 held out, TP 52, FP 3, TN 225, FN 20, precision 94.55%, recall 72.22% |
| Test suite | `live-integration-check-2026-10-25.json` | 79 Python tests, 20 subtests, 9 Node tests |
| Browser check | `browser-final-check-2026-10-25.json` | 0px overflow at 1280, 1024, 768 and 390; 7 links per view; no default-blue links |

## Claims deliberately kept narrow

- Gemma's full expense task remains 0/5; the small smoke compile is not a full-task success.
- The 20/20 verifier result is the same mutation set after adding fixtures for the two original misses.
- TabPFN is synthetic, supervised and advisory.
- Temporal is local recovery evidence, not production durability.
- Mastra/Groq proposal and verification worked, but the latest smoke check did not approve the candidate.
- Sentry local SDK/redaction worked; external delivery and a clean screenshot are not claimed.
- No hosted demo or outside-user validation is claimed.
