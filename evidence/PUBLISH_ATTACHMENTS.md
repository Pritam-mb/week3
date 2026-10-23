# Publication attachment map

Use this map when moving `POST_DRAFT.md` into the publishing editor.

## Attach

1. **Pipeline image** — `evidence/pipeline.png`
   - Place after the “Teach → Gemma proposes…” lifecycle paragraph.
   - It is a conceptual diagram, not a live dashboard screenshot.

2. **Molt dashboard screenshot** — optional
   - Place at the dashboard image slot after the lifecycle evidence.
   - Upload only if all CSV values, prompts, responses, local paths,
     credentials and account details are hidden.
   - No safe dashboard screenshot is currently recorded, so leaving this slot
     empty is safer than publishing sensitive data.

3. **Temporal UI screenshot** — optional
   - Place after the Temporal paragraph.
   - Use only if a real screenshot of the completed workflow was captured.
   - If unavailable, leave the slot empty and keep the narrower JSON-backed
     claim: fixture recipe, four-row input, three output rows, zero model calls.

## Do not attach

- **Sentry screenshots:** the inspected trace contained sensitive CSV values and
  local file paths. Sentry is implemented, but its trace is intentionally not
  shown.
- **TabPFN dashboard screenshot:** the evaluation ran locally on CPU with
  telemetry disabled. Use `TABPFN_PROOF.md` and `tabpfn-accuracy.json`.
- **Raw Gemma/SQLite/debug screenshots:** the JSON evidence and tables are the
  safer proof.

Before publishing, replace repository-relative image references with uploaded
images if the publishing editor cannot resolve them. Do not publish this guide
itself.
