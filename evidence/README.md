# Molt Evidence Index

This directory contains evidence summaries, sanitized recipe examples, and a
conceptual pipeline illustration. Recipe JSON is explicitly model-generated
evidence; scalar task constants are not raw CSV row dumps. No credential values
are intentionally exported. Consult `repo-hygiene.json` for unresolved historical
credential-pattern matches rather than treating this as a repository security certification.

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

- `gemma-full-task-followup.json` — separate warm-model, 120-second-timeout
  follow-up: five trials, zero passes, 15 generation requests. Trial 3/4 final
  outcomes were recovered from SQLite after JSON file-lock failures. Original
  ladder files are unchanged. This is not pass@5; each new trial allows three requests.
- `verifier-catch-rate-after.json` — exact historical mutations recovered from
  the session command: before 18/20, after 20/20; schema vs fixture catches are
  separated. Reproduce with `python verifier_measurement.py --check`.
- `tabpfn-accuracy.json` — live synthetic supervised holdout confusion matrix,
  precision, recall and false positives. Reproduce with `tabpfn_accuracy.py`.
- `TABPFN_PROOF.md` — explains why there is no hosted dashboard receipt and
  maps the local TabPFN run to its code, metrics and privacy boundary.
- `PUBLISH_ATTACHMENTS.md` — exact image slots and the screenshots that must
  not be uploaded.
- `pipeline.svg` — conceptual illustration, not a live dashboard screenshot.
- `pipeline.png` — browser-rendered PNG of the same illustration, visually
  inspected locally and ready for upload to a post editor.
- `POST_AUDIT.md` — numeric claim-to-source map and check results.
- `submission-checks.json` — offline demo with credentials removed and socket
  connections forbidden, local links and tags checked; not publishing-site validation.
- `CAPTURE_CHECKLIST.md` — capture and publication status, including completed
  Sentry review/rotation and remaining manual publication tasks. Sentry is
  implemented but omitted from the post because the inspected trace contained
  sensitive CSV values and local paths.
- `repo-hygiene.json` — read-only local-ref Git scan; current known credentials
  not found, but historical credential-shaped strings need private review.

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
