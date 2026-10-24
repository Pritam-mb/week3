(function () {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const api = (path) => `/api${path}`;
  const L = (value, fallback = "—") => value === undefined || value === null || value === "" ? fallback : String(value);
  const escapeHTML = (value) => L(value, "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const fileName = (value) => L(value, "workspace file").split(/[\\/]/).pop();
  const formatDate = (value) => { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); };
  const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
  const setStatus = (message, kind = "") => { const target = $("#diff-status"); target.className = `diff-status ${kind}`; target.textContent = message; };
  const row = (label, value) => `<div class="evidence-row"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`;
  const list = (values) => Array.isArray(values) && values.length ? `<ul class="inspector-list">${values.slice(0, 12).map((value) => `<li>${escapeHTML(value)}</li>`).join("")}</ul>` : "";

  async function request(path) {
    const response = await fetch(api(path), { headers: { Accept: "application/json" } });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) throw new Error(payload?.error?.message || `Request failed (${response.status})`);
    return payload;
  }

  function render(run, automation) {
    const blocked = String(run.status).toUpperCase() === "BLOCKED_DRIFT";
    const version = (automation?.versions || []).find((item) => item.id === run.recipe_version_id);
    const recipe = version?.recipe || {};
    const details = run.error_details || {};
    document.title = `${blocked ? "Blocked drift" : "Succeeded"} · ${fileName(run.input)} · molt evidence`;
    const cards = [
      [blocked ? "BLOCKED_DRIFT" : "SUCCEEDED", "Molt decision", blocked ? "bad" : "ok"],
      [number(run.rows_read), "Rows read", ""],
      [number(run.rows_written), "Rows written", blocked ? "bad" : "ok"],
      [number(run.llm_calls), "Model calls at run time", ""],
      [run.duration_ms ? `${number(run.duration_ms)} ms` : "—", "Execution time", ""],
    ];
    $("#evidence-cards").innerHTML = cards.map(([value, label, tone]) => `<div class="evidence-card ${tone}"><strong>${escapeHTML(value)}</strong><span>${escapeHTML(label)}</span></div>`).join("");
    $("#before-badge").textContent = blocked ? "mismatch" : "accepted";
    $("#before-badge").className = `diff-badge ${blocked ? "bad" : "ok"}`;
    $("#after-badge").textContent = blocked ? "no output" : "written";
    $("#after-badge").className = `diff-badge ${blocked ? "bad" : "ok"}`;
    $("#before-content").className = "diff-content";
    $("#before-content").innerHTML = row("Input file", fileName(run.input)) + row("Input fingerprint", run.file_fingerprint || "recorded") + row("Schema fingerprint", run.schema_fingerprint || "recorded") + row("Rows received", number(run.rows_read)) + row("Recipe expected", version ? `v${version.version_number}` : run.recipe_version_id || "—");
    $("#after-content").className = "diff-content";
    $("#after-content").innerHTML = blocked ? row("Output", "Not written") + row("Quarantine", "Created for review") + row("Error code", run.error_code || "DRIFT") + `<div class="safe-note bad">Molt stopped here instead of guessing. The existing approved recipe remains unchanged.</div>` : row("Output file", fileName(run.output)) + row("Output rows", number(run.rows_written)) + row("Model calls", number(run.llm_calls)) + `<div class="safe-note">The approved recipe ran deterministically. The model was not called again.</div>`;
    const traces = [];
    traces.push([true, "Input contract", blocked ? "The new file did not match the approved contract." : "Required structure accepted."]);
    traces.push([!blocked, blocked ? (run.error_code || "Drift detected") : "Recipe execution", blocked ? (run.error_message || "The file was blocked before output.") : "The deterministic interpreter applied the approved operations."]);
    traces.push([!blocked, "Output policy", blocked ? "No output was written; the input was quarantined." : "Output was written atomically without overwriting an existing file."]);
    if (details.missing) traces.push([false, "Missing columns", list(details.missing)]);
    if (details.extra) traces.push([false, "Unexpected columns", list(details.extra)]);
    if (details.column) traces.push([false, "Affected column", escapeHTML(details.column)]);
    if (details.unmapped_count) traces.push([false, "Unmapped rows", escapeHTML(details.unmapped_count)]);
    $("#decision-trace").innerHTML = traces.map(([ok, title, detail]) => `<div class="trace-item ${ok ? "" : "bad"}"><span class="trace-mark">${ok ? "✓" : "×"}</span><strong>${escapeHTML(title)}</strong><span>${detail}</span></div>`).join("");
    $("#trace-caption").textContent = `${fileName(run.input)} · ${formatDate(run.started_at)}`;
    const operations = recipe.operations || [];
    $("#recipe-content").className = "recipe-evidence";
    $("#recipe-content").innerHTML = `<div class="recipe-meta"><div><strong>v${escapeHTML(version?.version_number || "—")}</strong><span>recipe version</span></div><div><strong>${escapeHTML(version?.status || "—")}</strong><span>stored status</span></div><div><strong>${escapeHTML(recipe.input_contract?.required_columns?.length || "—")}</strong><span>required columns</span></div></div><div class="recipe-steps">${operations.length ? operations.map((operation) => `<span class="recipe-step">${escapeHTML(operation.type)}</span>`).join("") : `<span class="empty">Recipe details unavailable for this run.</span>`}</div>`;
    setStatus(blocked ? "This evidence shows a deliberate drift block. The recipe did not silently adapt." : "This evidence shows a compatible deterministic reuse run.", blocked ? "blocked" : "success");
  }

  async function load(runId) {
    if (!runId) { setStatus("Enter a run ID or open this page from a dashboard run.", "error"); return; }
    setStatus("Loading stored run evidence…");
    try {
      const run = await request(`/runs/${encodeURIComponent(runId)}`);
      const automation = run.automation_id ? await request(`/automations/${encodeURIComponent(run.automation_id)}`) : null;
      render(run, automation);
      $("#run-id").value = run.id || runId;
      $("#dashboard-link").href = `/?run=${encodeURIComponent(run.id || runId)}`;
    } catch (error) { setStatus(error.message, "error"); }
  }

  $("#load-run").addEventListener("click", () => load($("#run-id").value.trim()));
  $("#run-id").addEventListener("keydown", (event) => { if (event.key === "Enter") load($("#run-id").value.trim()); });
  const preferred = localStorage.getItem("molt-theme");
  const setTheme = (theme) => { document.documentElement.dataset.theme = theme; localStorage.setItem("molt-theme", theme); $("#theme-button").textContent = theme === "dark" ? "Light theme" : "Dark theme"; };
  setTheme(preferred || (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  const params = new URLSearchParams(window.location.search);
  const requestedRun = params.get("run");
  if (requestedRun) { $("#run-id").value = requestedRun; load(requestedRun); }
}());
