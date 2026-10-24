# Post audit — submission pass

## Final implementation addendum — 2026-10-24

The next writing pass should use the user's **Slow and steady** theme. The draft
has not yet been rewritten for the following additions:

- `temporal-chaos.json`: two worker SIGKILLs and one persistent local Temporal
  server SIGKILL/restart; recovery on attempt 3; two oracle-matching compatible
  outputs; one drift block with one attempt; replay without output replacement;
  zero execution model calls. Fixture recipe, scripted approval, deterministic
  barriers, retained local workspace. Not Cloud, random kills, model-call retries,
  power-loss testing or production durability.
- Gemma guardrails: strict JSON/nested-field/profile checks, bounded attempt
  summaries, early stop for unfixable setup errors. Regression-tested with
  controlled responses; **no new live Gemma accuracy measurement**.
- `verifier-final-guardrails.json`: current-code source hashes and unchanged
  18/20 → same mutations 20/20 results. The older default snapshot check differs
  only in source hashes; preserve the historical files.
- Current Python suite: 78 passed, 20 subtests passed, one pre-existing `cgi`
  warning. Dashboard behavior: 3 Node tests passed (mock DOM, not visual review).

Details and reproduction commands: `SLOW_AND_STEADY_HANDOFF.md`.

## Claim-to-source map

| Claim in POST_DRAFT.md | Source | Boundary |
|---|---|---|
| Live trim: 6 checks, 4 rows, zero execution model calls, 157.45 ms | `lifecycle.json` | Earlier single run; activation scripted, not independent human review |
| Original ladder: 5/5, 4/5, 3/5, 0/5 first-request successes | `gemma-ladder.csv`, rung JSON | Temperature zero, repeated tasks, different timeouts/budgets; not general pass@k |
| Full task follow-up: 0/5, 15 requests, 14 rejected recipes, 1 timeout | `gemma-full-task-followup.json` | Expanded fixtures, shorter prompt, 120s timeout; trial 3/4 outcome recovery disclosed |
| Rejected model candidate only trims | `gemma-rung3-rejected-candidate.json` | Its own prose is not trusted as operation evidence |
| Original 18/20 → expanded suite 20/20; correct control 11/11 | `verifier-catch-rate.json`, `verifier-catch-rate-after.json` | Exact inline mutations recovered; 15 fixture catches + 5 schema rejections |
| Seed 41; four drift cases; 3 silent wrong outputs; 2 blocks/quarantines; 2/2 successful Molt outputs matched oracle | `benchmark.json` | Naive baseline; renamed-column case correct for baseline but blocked by Molt |
| Historical approved repair 8/8 | `lifecycle.json` | Separate fixture-backed record, not proven live Gemma repair |
| TabPFN: 300 holdout, TP52/FP3/TN225/FN20, precision94.55%, recall72.22% | `tabpfn-accuracy.json` | Synthetic, supervised, advisory; not real-world validation |
| Temporal live plus crash/retry: fixture recipe, four input rows, three outputs, zero model calls; one injected failure, two attempts, checkpoint resumed | `tabpfn-temporal-live.json`, `temporal-crash-recovery.json` | Not Gemma-generated; local dev server/worker evidence, not production durability |
| Sentry implementation | Screenshot pending local save | Root and child spans inspected; nine aggregate-only stages visible and no CSV values/prompts/responses/paths/credentials visible; DSN rotation is user-reported and not independently verifiable from the repository |
| Offline demo without .env/network/credentials | `submission-checks.json` | Fresh temp workspace, existing Python installation; socket connects forbidden |

The historical ladder and original 18/20 evidence were not overwritten. New
results are separate files. Publication must upload the PNG separately if the
platform cannot resolve repository-relative image links.

## Checks run in this session

From the repository, with `.env.example` and no Sentry DSN for the test process:

- `python -m unittest discover -s tests -v`: PASS, 66 tests.
- `python verifier_measurement.py --check`: PASS, saved result reproducible;
  historical outcome mismatch list empty.
- `python bench.py`: PASS, behavior counts match existing benchmark evidence.
- `python -m compileall -q molt tests bench.py verifier_measurement.py tabpfn_accuracy.py gemma_full_task_rerun.py hygiene_scan.py submission_check.py`: PASS.
- `node --check molt/web/app.js`: PASS (syntax, not browser behavior).
- `git diff --check`: PASS.
- `python submission_check.py`: PASS, offline demo, local links, SVG parse, JSON,
  both challenge tags. No publication-site/image-upload claim.
- Real TabPFN evaluation: PASS, aggregate results and source hashes recorded.
- Full-task live Gemma follow-up: completed, **no passing candidate**; not a passing feature test.
- No dedicated linter/typechecker run; no separate packaging build run.

## Blockers before publication

`repo-hygiene.json` found no tracked private `.env` and no reachable-history
matches for the current local TabPFN token or Sentry DSN. It also found two
credential-shaped historical strings, in `workflow.txt` and an old `.env.example`.
The `workflow.txt` match remains in the current tree. They need private review
and revocation if real; absence of current-value matches is not a clean bill
of health. No credentials are printed here. No history rewrite was performed.

Temporal UI was unavailable (headless server); no UI screenshot is claimed.
Dashboard capture, external reader review and publishing-preview checks remain
manual. See `CAPTURE_CHECKLIST.md`. Nothing was committed, pushed, or published
by this submission pass.
