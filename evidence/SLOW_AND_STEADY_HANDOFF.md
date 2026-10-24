# Slow and steady — final technical handoff

Date: 2026-10-24. The user confirmed Week 3's theme as **Slow and steady**.
This is implementation/evidence material for the next post pass, not a new
contest-rules or category-eligibility audit.

## Stop point

The requested final engineering pass is complete. Keep Temporal local. No Cloud
account, payment, additional sponsor, staged compiler, or new Gemma trial was
needed. Next work is writing/reviewing the post and closing publication checks.

The defensible theme connection:

> Spend effort verifying the recipe once. Reuse it without repeated inference.
> After an interruption, resume completed work; when the input changes, stop
> rather than guess.

## What the Temporal experiment actually did

Reproduce with an installed Temporal CLI and optional Python SDK:

```text
python temporal_chaos.py
```

If needed, pass `--temporal-cli <path-to-executable>`. This session used the
already-installed SDK dev-server executable in the container, not a Cloud
endpoint. The script uses a fresh temporary workspace and cleans up its own
server/worker processes. It does not kill a user's running services or read `.env`.

| Observation | Recorded result |
|---|---|
| Worker process kills | 2 SIGKILLs, after completed checkpoints 1 and 2 |
| Temporal server process kill | 1 SIGKILL; restarted against the same SQLite file |
| Interrupted activity | Completed on attempt 3 |
| Completed checkpoint files | Steps 1 and 2 retained the same bytes and modification times |
| Compatible files | 2 outputs matched separately authored expected CSVs |
| Drift file | BLOCKED_DRIFT, quarantined, no output, 1 activity attempt |
| Replay | Existing execution record returned; no output replacement |
| Execution records | 3 for the 3 source files, despite the extra replay workflow |
| Model calls during execution | 0 |
| Source bytes | Preserved for all three inputs |

Source: `temporal-chaos.json`. The real POST start and GET status HTTP routes are
used. Worker execution uses the production workflow/activity; a test-only pause
after checkpoint publication makes the kill timing reproducible. The harness
automatically restarts processes. Do not call these random kills or nine kills.

The recipe is the checked-in synthetic expense fixture, independently verified
then **script-approved** for the experiment. This is not live Gemma generation
or independent human approval. Temporal orchestrates approved deterministic
execution; compilation/model calls are outside the workflow. There is no model
API retry/cache or “never bought a reply twice” claim.

Local state and the approved recipe/input were retained and unchanged across
restarts. This does not test power loss, disk loss, changing approvals mid-flight,
multi-host writes, a production cluster, or Temporal Cloud.

## Fixes that made the recovery boundary stronger

- `molt/core.py`: checkpoint JSON is written via a flushed temporary file and
  atomic replacement. CSV temp files are flushed before publication.
- `molt/application.py`: final outputs use atomic no-replace publication. A retry
  after publication but before SQLite recording can reconcile identical output
  from a completed checkpoint without replacing it. A different existing output
  is rejected. Retained local disk is required.
- `molt/temporal.py`: completed workflow descriptions include allowlisted aggregate
  results, so a blocked drift outcome is not confused with successful output.
- `molt/web/app.js`, `molt/web/index.html`: durable-run status polling, reload
  recovery for the latest workflow ID, and bounded polling with manual Refresh.
  Unapproved recipes cannot launch through the button. Model readiness reflects
  the actual readiness status rather than a non-empty status string.
- The dashboard now exposes the whole user lifecycle instead of only results:
  create automation, choose/upload input, profile, compile with Gemma or the
  checked-in fixture, run tests, approve, then run compatible files. It also
  explains that Gemma proposes a stored recipe rather than remembering a user,
  renders a five-stage contract graph, and lets a user click any run to inspect
  the structural reason for a drift block without showing raw cell values.
- Added `/diff.html`, a stored-evidence page linked from the dashboard and from
  each run row. It presents Before/After cards, decision trace, recipe steps,
  output/quarantine result, and structural mismatch details. It intentionally
  excludes raw CSV samples and values; it is a decision diff, not a data viewer.
- `temporal_crash_recovery.py`: replaced incorrect hand-written numeric event
  labels with Temporal's protobuf enum. Retry count comes from the activity's
  attempt field, since intermediate retries need not appear as separate started
  events. The smaller exception/retry check was rerun successfully.

## What changed for Gemma

`molt/ollama.py`, `molt/core.py`, `molt/application.py`, `molt/privacy.py` now
provide the additional rejection boundaries:

- Reject duplicate JSON keys, non-finite constants, fenced prose, incomplete
  responses, and malformed nested recipe fields.
- Validate unique column lists, supported operation types and argument types.
- Reject contracts requiring nonexistent input columns or forbidding existing
  extra columns before storing a candidate.
- Preserve the existing fixture/invariant verifier and mandatory approval gate.
- Keep one generation/verification retry budget (default: three requests total).
  Missing-model and oversized-prompt errors stop without pointless retries.
- Attach per-attempt codes/stages/counts to a version or terminal error. Feedback
  does not include raw fixture values, response bodies or filesystem paths.
- Failed compilation leaves the approved active recipe untouched.

This is a tested safety improvement, **not a measured improvement in Gemma's
success rate**. Controlled fake provider responses exercise malformed → rejected
→ corrected sequences in regression tests. No new live Gemma trial was run.
The historical full task remains **0/5**. The verifier still depends on fixture
coverage; passing fixtures is not a guarantee over every possible input.

## Checks and evidence preservation

- `python -m pytest -q`: 78 passed, 20 subtests passed; one existing Python `cgi`
  deprecation warning.
- `node --test tests/test_dashboard.cjs`: 5 dashboard behavior tests passed.
  These use a mock DOM/network, not a visual browser or screenshot claim.
- `node --test tests/test_dashboard.cjs tests/test_diff_page.cjs`: 7 tests passed;
  the diff assets were also served successfully at `/diff.html`, `/diff.css`,
  and `/diff.js` from the local API.
- `node --check molt/web/app.js`: passed.
- `python -m compileall -q molt tests temporal_crash_recovery.py temporal_chaos.py`: passed.
- `python temporal_crash_recovery.py`: COMPLETE, 2 activity attempts.
- `python temporal_chaos.py --temporal-cli <installed-executable>`: COMPLETE.
- `python bench.py`: both successful Molt outputs match the independent oracle.
- `python verifier_measurement.py --check --output evidence/verifier-final-guardrails.json`: passed.
- `python submission_check.py`: passed; offline demo with sockets forbidden,
  13 draft-local links present, tags present. Not a publishing-preview check.
- Focused `git diff --check` for edited source/tests/docs: passed. Unrelated
  pre-existing `workflow.txt` whitespace has not been cleaned up.

The default verifier snapshot check reported a mismatch because `core.py` and
`application.py` source hashes changed. Comparison confirmed **only** the
`source_sha256` section differs: original fixtures still catch 18/20; expanded
fixtures catch the same 20/20 mutations; the correct recipe passes 11/11.
Historical reports were not replaced. The separate current snapshot is
`verifier-final-guardrails.json`. Do not imply an unseen evaluation set.

## Next: the post, not more features

Use one story: verified once → quiet reuse → interrupted → resumed → drift
blocked. Keep the full Gemma **0/5**, TabPFN **72.22% recall**, and original
verifier **18/20** visible. Do not invent customers, revenue, energy savings,
Cloud screenshots, or model-quality improvements.

`POST_DRAFT.md` has not yet been rewritten for this final evidence. Publication
still requires the private credential-history review, consistent Sentry wording
and saved clean screenshot, actual visual captures if used, fresh-clone check,
outside-reader review, and publishing preview. No Git commit/push or publication
was performed by this pass.
