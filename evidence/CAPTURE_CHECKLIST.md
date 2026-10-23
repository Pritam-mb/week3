# Submission capture checklist

## Saved evidence (not screenshots)

- Live trim approval-state and zero-call execution: `lifecycle.json`.
  Activation was scripted; do not label it independent human review.
- Rejected live candidate: `gemma-rung3-rejected-candidate.json` (only trim,
  despite a broader description; `golden_output` failed).
- Original ladder: `gemma-ladder.csv` and per-rung JSON. Preserve unchanged.
- Drift block and fixture repair: `lifecycle.json`, `benchmark.json`.
  These are separate runs, not one complete live Gemma repair sequence.
- Pipeline image: `pipeline.svg` — conceptual illustration, not a live capture.
  `pipeline.png` is the browser-rendered upload version; visually inspected.
- TabPFN: `tabpfn-accuracy.json` — synthetic, supervised, advisory.
- Temporal: `tabpfn-temporal-live.json` — live fixture recipe, four input rows,
  zero model calls; no demonstrated crash recovery.

## Manual captures still required

- [ ] Inspect and capture the live dashboard with CSV values, paths, prompts,
  model response bodies, credentials, browser account details hidden.
- [ ] Temporal UI workflow: current server was started headless; UI port 8233
  was not reachable at this audit. Do not fabricate a UI screenshot or restart
  a busy server merely for a picture. CLI completion evidence already exists.
- [x] Sentry: the live Molt workflow trace was inspected. It contained
  sensitive CSV values and local file paths, so it is **not publishable**. Do
  not use or upload any Sentry screenshot. The local screenshot was removed
  from `evidence/`; Sentry remains implemented, but the trace is intentionally
  omitted from the post. The old DSN was rotated/disabled and the replacement
  remains private in local config.
- [ ] Review historical credential-shaped matches reported in
  `repo-hygiene.json`; revoke old credentials if real. Do not paste them in chat.
- [ ] Ask a person to read `POST_DRAFT.md` and state its point in one sentence.
- [ ] Check images and links in the actual publishing preview; local link checks
  are not proof the publishing platform has uploaded images correctly.

No external review or publication is claimed complete. Sentry review and DSN
rotation are complete; Sentry evidence is intentionally not included because
the inspected trace contained sensitive data.
