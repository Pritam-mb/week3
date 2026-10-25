# Publication attachment map

Use this map when moving `POST_DRAFT.md` into the publishing editor.

## Attach

1. **Pipeline image** — `evidence/pipeline.png`
   - Place after the “Teach → Gemma proposes…” lifecycle paragraph.
   - It is a conceptual diagram, not a live dashboard screenshot.

2. **Molt dashboard screenshot** — `evidence/dashboard_live.png`
   - Place at the dashboard image slot after the demo section.
   - Verified 100% sanitized: all raw CSV values, credentials, and paths are hidden.
   - Shows the live run beads, 0 runtime model calls chart, candidate approval state, and ready sidecars.

3. **Sentry trace screenshot** — `evidence/sentry-trace.png`
   - Verified 100% sanitized: all spans show only clean lifecycle stage names and latency.
   - Shows all 9 spans in the waterfall executing in ~50ms total root duration.
   - Zero CSV row values, zero credentials, zero local paths.

4. **Temporal UI screenshot** — optional
   - Place after the Temporal paragraph.
   - Use only if a real screenshot of the completed workflow was captured.
   - If unavailable, leave the slot empty and keep the narrower JSON-backed
     claim: fixture recipe, four-row input, three output rows, zero model calls.

## Do not attach

- **TabPFN dashboard screenshot:** the evaluation ran locally on CPU with
  telemetry disabled. Use `TABPFN_PROOF.md` and `tabpfn-accuracy.json`.
- **Raw Gemma/SQLite/debug screenshots:** the JSON evidence and tables are the
  safer proof.

Before publishing, replace repository-relative image references with uploaded
images if the publishing editor cannot resolve them. Do not publish this guide
itself.
