# Molt Evidence Index

All files in this directory are sanitized evidence artifacts. They contain no
CSV row values, prompts, model responses, credentials, local paths, or Sentry
DSNs.

## Live Gemma ladder

- `gemma-ladder.csv` — five attempts for each task rung.
- `gemma-ladder-rung1.json` through `gemma-ladder-rung4.json` — raw bounded
  result summaries with verification outcomes and latency.
- `gemma-rung1-passing-recipe.json`, `gemma-rung2-passing-recipe.json`, and
  `gemma-rung3-passing-recipe.json` — passing live candidate recipes.
- `gemma-rung3-rejected-candidate.json` — one rejected candidate and its failed
  verification check.

Rung 4 timed out in all five attempts before a provider response envelope was
returned. Its model-call count is intentionally recorded as `unknown`, not
zero.

## Lifecycle proof

- `lifecycle.json` — approved live candidate, 6/6 verification, zero-call
  reuse, drift block/quarantine, and an approved verified repair. It contains
  IDs and counts only.
- `benchmark.json` — fixed-seed naive positional baseline and Molt drift
  measurement.
- `tabpfn-temporal-live.json` — sanitized live TabPFN supervised advisory
  inference and live Temporal workflow evidence.

## Claim boundary

The evidence supports a local verified lifecycle, a live TabPFN supervised
advisory run on a synthetic labeled fixture, and a live Temporal workflow using
an approved fixture recipe. The TabPFN result is not unlabeled anomaly
detection or real-world drift validation. The Temporal result is not live
Gemma generation. Call avoidance is an inference proxy, not a measurement of
electricity savings.
