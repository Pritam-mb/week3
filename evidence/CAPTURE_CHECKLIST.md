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
  zero model calls; `temporal-crash-recovery.json` additionally records a real
  local Temporal activity failure, retry and checkpoint resume.

## Manual captures still required

- [ ] Inspect and capture the live dashboard with CSV values, paths, prompts,
  model response bodies, credentials, browser account details hidden.
- [ ] Temporal UI workflow: current server was started headless; UI port 8233
  was not reachable at this audit. Do not fabricate a UI screenshot or restart
  a busy server merely for a picture. CLI completion evidence already exists.
- [~] Sentry: the root transaction and all child spans of the live Molt
  workflow trace were inspected. The trace showed nine expected stages,
  timings and generic status attributes; no CSV values, prompts, responses,
  paths or credentials were visible. The exposed DSN was reported rotated/
  disabled; account-side rotation is not independently verifiable from this
  repository. Save the clean screenshot as `evidence/sentry-trace.png` before
  linking it in the post; no screenshot is currently stored in the repository.
- [ ] Review historical credential-shaped matches reported in
  `repo-hygiene.json`; revoke old credentials if real. Do not paste them in chat.
- [ ] Ask a person to read `POST_DRAFT.md` and state its point in one sentence.
- [ ] Check images and links in the actual publishing preview; local link checks
  are not proof the publishing platform has uploaded images correctly.

No external review or publication is claimed complete. Sentry review and DSN
rotation are complete; Sentry evidence is intentionally not included because
the inspected trace contained sensitive data.
