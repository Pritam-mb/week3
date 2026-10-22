(function () {
  "use strict";

  const state = {
    health: null,
    metrics: {},
    automations: [],
    runs: [],
    versions: [],
    selectedAutomationId: null,
    selectedRun: null,
    profiles: {},
    loadErrors: []
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const api = (path) => `/api${path}`;

  function escapeHTML(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function safeJSON(value) {
    try { return JSON.stringify(value, null, 2); } catch (_) { return "{}"; }
  }

  function listFrom(value, keys) {
    if (Array.isArray(value)) return value;
    if (!value || typeof value !== "object") return [];
    for (const key of keys) if (Array.isArray(value[key])) return value[key];
    if (value.data && value.data !== value) return listFrom(value.data, keys);
    return [];
  }

  function objectFrom(value) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      if (value.data && typeof value.data === "object" && !Array.isArray(value.data)) return value.data;
      return value;
    }
    return {};
  }

  async function request(path, options) {
    const response = await fetch(api(path), Object.assign({ headers: { Accept: "application/json" } }, options || {}));
    let payload = null;
    const text = await response.text();
    if (text) {
      try { payload = JSON.parse(text); } catch (_) { payload = { message: text }; }
    }
    if (!response.ok) {
      const error = new Error((payload && (payload.message || payload.error || payload.detail)) || `Request failed (${response.status})`);
      error.payload = payload;
      error.status = response.status;
      throw error;
    }
    return payload || {};
  }

  function jsonRequest(path, method, body) {
    return request(path, {
      method,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
  }

  function firstValue(object, keys, fallback = null) {
    if (!object || typeof object !== "object") return fallback;
    for (const key of keys) if (object[key] !== undefined && object[key] !== null) return object[key];
    return fallback;
  }

  function numberValue(object, keys, fallback = 0) {
    const value = firstValue(object, keys, fallback);
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function formatNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString() : "—";
  }

  function formatDuration(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    if (number < 1000) return `${Math.round(number)} ms`;
    return `${(number / 1000).toFixed(number >= 10000 ? 1 : 2)} s`;
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function statusKind(value) {
    const status = String(value || "").toUpperCase();
    if (["SUCCEEDED", "SUCCESS", "PASS", "PASSED", "ACTIVE", "APPROVED", "VERIFIED", "ONLINE", "HEALTHY"].includes(status)) return "success";
    if (["BLOCKED_DRIFT", "DRIFT", "QUARANTINED", "PROPOSED", "CANDIDATE", "PENDING", "REVIEW", "DEGRADED"].includes(status)) return "warning";
    if (["FAILED", "ERROR", "REJECTED", "OFFLINE", "UNAVAILABLE"].includes(status)) return "error";
    return "neutral";
  }

  function statusPill(value, fallback = "Unknown") {
    const text = String(value || fallback).replace(/_/g, " ");
    const kind = statusKind(value);
    return `<span class="pill pill-${kind === "neutral" ? "neutral" : kind === "success" ? "green" : kind === "warning" ? "amber" : "red"}">${escapeHTML(text)}</span>`;
  }

  function statusText(value, fallback = "Unknown") {
    const text = String(value || fallback).replace(/_/g, " ");
    return `<span class="status-text ${statusKind(value)}">${escapeHTML(text)}</span>`;
  }

  function showToast(message, kind = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${kind}`;
    toast.textContent = message;
    $("#toast-region").appendChild(toast);
    window.setTimeout(() => toast.remove(), 4800);
  }

  function emptyState(icon, title, message, action = "") {
    return `<div class="empty-state"><div><div class="empty-icon" aria-hidden="true">${icon}</div><strong>${escapeHTML(title)}</strong><p>${escapeHTML(message)}</p>${action}</div></div>`;
  }

  function getAutomation(id = state.selectedAutomationId) {
    return state.automations.find((item) => String(item.id) === String(id));
  }

  function getMetric(keys, fallback = 0) {
    return numberValue(state.metrics, keys, fallback);
  }

  function normalizeAutomations(payload) {
    return listFrom(payload, ["automations", "items", "results"]);
  }

  function normalizeRuns() {
    const sources = [
      listFrom(state.metrics, ["runs", "recent_runs", "execution_runs"]),
      ...state.automations.map((automation) => listFrom(automation, ["runs", "recent_runs", "execution_runs"]))
    ];
    const seen = new Set();
    state.runs = sources.flat().filter((run) => {
      const key = String(run.id || run.run_id || `${run.started_at || ""}-${run.input_reference || run.input || ""}`);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).sort((a, b) => new Date(b.started_at || b.created_at || 0) - new Date(a.started_at || a.created_at || 0));
  }

  function pendingRecipe(automation) {
    if (!automation) return null;
    const direct = firstValue(automation, ["candidate", "candidate_recipe", "pending_recipe", "recipe_candidate", "draft_recipe"]);
    if (direct) return direct;
    const versions = listFrom(automation, ["recipe_versions", "versions"]);
    return versions.find((version) => ["CANDIDATE", "PROPOSED", "PENDING", "REVIEW", "VERIFIED"].includes(String(version.status || "").toUpperCase())) || null;
  }

  function recipePayload(candidate) {
    if (!candidate) return {};
    if (candidate.recipe && typeof candidate.recipe === "object") return candidate.recipe;
    if (candidate.recipe_json && typeof candidate.recipe_json === "object") return candidate.recipe_json;
    return candidate;
  }

  function collectEvidence(candidate) {
    const verification = firstValue(candidate, ["verification", "verification_run", "verification_result", "evidence"], {}) || {};
    const results = listFrom(verification, ["results", "checks", "test_results", "invariants"]);
    if (results.length) return results.map((item) => ({
      status: item.status || item.result || (item.passed === false ? "FAIL" : item.passed === true ? "PASS" : "PENDING"),
      name: item.fixture || item.check || item.name || "Verification check",
      detail: item.message || item.details || item.reason || ""
    }));
    const total = numberValue(verification, ["checks_total", "total"], 0);
    const passed = numberValue(verification, ["checks_passed", "passed"], 0);
    const failed = numberValue(verification, ["checks_failed", "failed"], 0);
    if (total || passed || failed) return [{ status: failed ? "FAIL" : passed === total ? "PASS" : "PENDING", name: "Verification suite", detail: `${formatNumber(passed)} of ${formatNumber(total)} checks passed` }];
    return [];
  }

  function renderHealth() {
    const health = objectFrom(state.health);
    const appStatus = firstValue(health, ["status", "app_status"], "unknown");
    const ollama = firstValue(health, ["ollama", "model", "ollama_status"], null);
    const online = statusKind(appStatus) === "success" || String(appStatus).toLowerCase() === "ok";
    const dot = $("#sidebar-health-dot");
    dot.className = `status-dot ${online ? "online" : state.loadErrors.includes("health") ? "offline" : ""}`;
    $("#sidebar-health-label").textContent = online ? "Local API online" : state.loadErrors.includes("health") ? "API unavailable" : "API status unknown";
    $("#sidebar-health-detail").textContent = ollama ? `Ollama ${String(typeof ollama === "object" ? firstValue(ollama, ["status", "name"], "ready") : ollama)}` : "Same-origin connection";
    const pill = $("#api-status-pill");
    pill.className = `pill ${online ? "pill-green" : state.loadErrors.includes("health") ? "pill-red" : "pill-neutral"}`;
    pill.textContent = online ? "API online" : state.loadErrors.includes("health") ? "API unavailable" : "API checking";
  }

  function renderMetrics() {
    const active = getMetric(["active_recipes", "active_versions", "active_automations"], state.automations.filter((item) => ["ACTIVE", "READY"].includes(String(item.status || "").toUpperCase())).length);
    const totalRuns = getMetric(["total_runs", "runs_count", "execution_runs"], state.runs.length);
    const quarantined = getMetric(["quarantined", "quarantined_files", "files_quarantined"], state.runs.filter((run) => statusKind(run.status) === "warning").length);
    const callsAvoided = getMetric(["calls_avoided", "llm_calls_avoided", "inference_avoided"], 0);
    const pendingRepairs = getMetric(["pending_repairs", "repairs_pending", "open_repairs"], state.automations.reduce((sum, item) => sum + listFrom(item, ["repair_proposals", "repairs"]).filter((repair) => !["APPROVED", "REJECTED"].includes(String(repair.status || "").toUpperCase())).length, 0));
    const duration = firstValue(state.metrics, ["median_duration_ms", "mean_duration_ms", "average_duration_ms"], null);
    const sample = getMetric(["duration_sample_size", "timing_sample_size", "sample_size"], 0);
    const cards = [
      ["Active recipes", active, "approved versions in use", "◇"],
      ["Runs recorded", totalRuns, `${formatNumber(quarantined)} quarantined`, "↗"],
      ["Inference avoided", callsAvoided, "against the declared baseline", "✦"],
      ["Runtime", duration == null ? "—" : formatDuration(duration), sample ? `${formatNumber(sample)} timing samples` : "no timing sample yet", "◷"]
    ];
    $("#metrics-grid").innerHTML = cards.map(([label, value, meta, icon]) => `<article class="metric-card"><div class="metric-label"><span>${escapeHTML(label)}</span><span class="metric-icon" aria-hidden="true">${icon}</span></div><div class="metric-value">${typeof value === "number" ? formatNumber(value) : escapeHTML(value)}</div><div class="metric-meta">${escapeHTML(meta)}</div></article>`).join("");
    $("#review-count").textContent = state.automations.filter((item) => pendingRecipe(item)).length;
    const openRepairs = state.automations.reduce((sum, item) => sum + listFrom(item, ["repair_proposals", "repairs"]).filter((repair) => !["APPROVED", "REJECTED"].includes(String(repair.status || "").toUpperCase())).length, 0);
    $("#drift-count").textContent = openRepairs;
  }

  function runName(run) {
    return firstValue(run, ["run_id", "id", "name"], "Unnamed run");
  }

  function renderRunRows(runs, limit) {
    const visible = limit ? runs.slice(0, limit) : runs;
    if (!visible.length) return emptyState("↗", "No runs yet", "Start a run from an active automation to see execution evidence here.");
    return `<table class="data-table"><thead><tr><th>Run</th><th>Automation</th><th>Status</th><th>Rows</th><th>Duration</th></tr></thead><tbody>${visible.map((run) => {
      const automation = getAutomation(firstValue(run, ["automation_id", "automation"]));
      const rows = `${formatNumber(firstValue(run, ["rows_written"], 0))} / ${formatNumber(firstValue(run, ["rows_read"], 0))}`;
      return `<tr class="clickable" data-run-id="${escapeHTML(run.id || run.run_id || "")}" title="Open run details"><td>${escapeHTML(runName(run))}<span class="table-sub">${escapeHTML(formatDate(firstValue(run, ["started_at", "created_at", "finished_at"])))}</span></td><td>${escapeHTML(automation ? firstValue(automation, ["name"], "Automation") : firstValue(run, ["automation_name", "automation_id"], "—"))}</td><td>${statusText(run.status)}</td><td>${rows}</td><td>${formatDuration(firstValue(run, ["duration_ms", "latency_ms"]))}</td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function renderOverviewRuns() { $("#overview-runs").innerHTML = renderRunRows(state.runs, 5); }

  function renderLedger() {
    const actual = getMetric(["actual_llm_calls", "llm_calls", "actual_execution_calls"], 0);
    const avoided = getMetric(["calls_avoided", "llm_calls_avoided", "inference_avoided"], 0);
    const baseline = getMetric(["baseline_llm_calls", "baseline_calls"], actual + avoided);
    const generation = getMetric(["generation_calls", "recipe_generation_calls", "compile_calls"], 0);
    const ratio = baseline > 0 ? Math.min(100, Math.max(0, (avoided / baseline) * 100)) : 0;
    $("#ledger-content").innerHTML = `<div><div class="ledger-number">${formatNumber(avoided)}</div><div class="ledger-caption">model calls avoided after recipe activation</div></div><div class="ledger-bar" aria-label="${Math.round(ratio)} percent of baseline calls avoided"><span style="width:${ratio}%"></span></div><div class="ledger-pairs"><div class="ledger-pair"><strong>${formatNumber(actual)}</strong><small>actual calls</small></div><div class="ledger-pair"><strong>${formatNumber(generation)}</strong><small>compile / repair overhead</small></div></div><div class="ledger-caption">${baseline ? `${formatNumber(baseline)} calls in declared baseline · values from ledger` : "No baseline events recorded yet."}</div>`;
  }

  function renderAutomations() {
    const container = $("#automations-list");
    if (!state.automations.length) {
      container.innerHTML = emptyState("◇", "No automations yet", "Create a draft to profile a CSV and generate your first constrained recipe.", `<button class="button button-primary button-small" type="button" data-open-create style="margin-top:14px">+ Create automation</button>`);
      $("#automation-detail").innerHTML = emptyState("·", "Select a workflow", "Automation details, versions, and run actions will appear here.");
      return;
    }
    container.innerHTML = state.automations.map((automation, index) => {
      const active = String(automation.status || "").toUpperCase() === "ACTIVE" || automation.active_version_id;
      const selected = String(automation.id) === String(state.selectedAutomationId);
      const candidate = pendingRecipe(automation);
      return `<article class="automation-card ${selected ? "selected" : ""}" tabindex="0" role="button" data-automation-id="${escapeHTML(automation.id || index)}"><div class="automation-avatar">${escapeHTML(String(firstValue(automation, ["name"], "M")).charAt(0).toUpperCase())}</div><div class="automation-copy"><div class="automation-name">${escapeHTML(firstValue(automation, ["name", "title"], "Untitled automation"))}</div><p class="automation-description">${escapeHTML(firstValue(automation, ["description", "task_description"], "No task description"))}</p><div class="automation-meta"><span>${active ? "Active recipe" : escapeHTML(firstValue(automation, ["status"], "Draft"))}</span>${candidate ? `<span>·</span><span class="status-text warning">Review needed</span>` : ""}</div></div><span class="automation-arrow" aria-hidden="true">›</span></article>`;
    }).join("");
    renderAutomationDetail();
  }

  function renderAutomationDetail() {
    const automation = getAutomation();
    const panel = $("#automation-detail");
    const runButton = $("#run-selected-button");
    runButton.disabled = !automation || !automation.active_version_id && String(automation.status || "").toUpperCase() !== "ACTIVE";
    if (!automation) { panel.innerHTML = emptyState("·", "Select a workflow", "Automation details, versions, and run actions will appear here."); return; }
    const candidate = pendingRecipe(automation);
    const versions = state.versions.length ? state.versions : listFrom(automation, ["recipe_versions", "versions"]);
    const activeVersion = firstValue(automation, ["active_version", "active_version_id", "version"], null);
    const profile = state.profiles[automation.id];
    const profileSummary = profile ? `<div class="profile-summary"><p class="eyebrow">PROFILED INPUT</p><strong>${formatNumber(profile.row_count)} rows · ${formatNumber(profile.column_count || (profile.columns || []).length)} columns</strong><small>Fingerprint ${escapeHTML(profile.schema_fingerprint || "recorded")}</small><pre class="code-preview">${escapeHTML(safeJSON({ columns: profile.columns, inferred_types: profile.inferred_types, null_counts: profile.null_counts, sample: profile.sample }))}</pre></div>` : `<p class="table-sub">No profile loaded yet. Profile a CSV before compiling.</p>`;
    panel.innerHTML = `<div class="detail-title"><div><p class="eyebrow">SELECTED AUTOMATION</p><h3>${escapeHTML(firstValue(automation, ["name", "title"], "Untitled automation"))}</h3></div>${statusPill(automation.status || (activeVersion ? "ACTIVE" : "DRAFT"))}</div><p class="detail-description">${escapeHTML(firstValue(automation, ["description", "task_description"], "No task description provided."))}</p><div class="detail-stats"><div class="detail-stat"><strong>${escapeHTML(activeVersion && typeof activeVersion === "object" ? firstValue(activeVersion, ["version_number", "version", "id"], "—") : activeVersion || "—")}</strong><small>active version</small></div><div class="detail-stat"><strong>${formatNumber(versions.length)}</strong><small>recipe versions</small></div></div>${profileSummary}<div class="detail-actions"><button class="button button-secondary button-small" type="button" data-action="profile">Profile CSV</button>${candidate ? `<a class="button button-primary button-small" href="#recipe-review" data-nav="recipe-review">Review candidate</a>` : `<button class="button button-primary button-small" type="button" data-action="generate">Generate recipe</button>`}</div>`;
  }

  function renderRecipeReview() {
    const automation = getAutomation();
    const candidate = pendingRecipe(automation);
    const pill = $("#recipe-status-pill");
    if (!candidate) {
      pill.className = "pill pill-neutral";
      pill.textContent = "No candidate selected";
      $("#recipe-review-content").innerHTML = emptyState("✓", "Nothing waiting for review", "Generate a recipe from an automation draft. Verification evidence and approval controls will appear here.", `<button class="button button-primary button-small" type="button" data-nav="automations" style="margin-top:14px">View automations</button>`);
      return;
    }
    const verification = firstValue(candidate, ["verification", "verification_run", "verification_result"], {}) || {};
    const verificationStatus = firstValue(verification, ["status"], firstValue(candidate, ["status"], "CANDIDATE"));
    pill.className = `pill pill-${statusKind(verificationStatus) === "success" ? "green" : statusKind(verificationStatus) === "error" ? "red" : "amber"}`;
    pill.textContent = String(verificationStatus).replace(/_/g, " ");
    const recipe = recipePayload(candidate);
    const evidence = collectEvidence(candidate);
    const operations = listFrom(recipe, ["operations", "steps"]);
    const operationText = operations.length ? operations.map((op) => firstValue(op, ["operation", "op", "name"], "operation")).join(" → ") : firstValue(recipe, ["operation_summary", "summary"], "Constrained recipe awaiting inspection");
    const assumptions = firstValue(recipe, ["assumptions", "failure_policy", "unknown_value_policy"], "Declared by the candidate recipe");
    const candidateId = firstValue(candidate, ["id", "recipe_version_id", "version_id"], firstValue(automation, ["candidate_recipe_id", "candidate_version_id"], ""));
    $("#recipe-review-content").innerHTML = `<article class="panel review-main"><div class="review-title"><div><p class="eyebrow">${escapeHTML(firstValue(automation, ["name"], "AUTOMATION"))}</p><h3>Candidate recipe ${escapeHTML(firstValue(candidate, ["version_number", "version"], ""))}</h3><span class="review-subtitle">${escapeHTML(firstValue(candidate, ["created_from", "source"], "initial proposal"))} · ${escapeHTML(formatDate(firstValue(candidate, ["created_at", "createdAt"])))}</span></div>${statusPill(verificationStatus)}</div><dl class="recipe-summary"><div class="recipe-row"><dt>Operations</dt><dd>${escapeHTML(operationText)}</dd></div><div class="recipe-row"><dt>Contracts</dt><dd>${escapeHTML(firstValue(recipe, ["input_contract", "input_schema", "schema_fingerprint"], "Input contract is recorded with this recipe"))}</dd></div><div class="recipe-row"><dt>Assumptions</dt><dd>${escapeHTML(typeof assumptions === "object" ? safeJSON(assumptions) : assumptions)}</dd></div></dl><p class="eyebrow">RECIPE JSON</p><pre class="code-preview">${escapeHTML(safeJSON(recipe))}</pre><div class="review-actions"><button class="button button-secondary button-small" type="button" data-action="verify-recipe" data-recipe-id="${escapeHTML(candidateId)}">Run verification</button><button class="button button-primary button-small" type="button" data-action="approve-recipe" data-recipe-id="${escapeHTML(candidateId)}" ${String(verificationStatus).toUpperCase() !== "PASS" && String(verificationStatus).toUpperCase() !== "VERIFIED" ? "disabled title=\"Verification must pass first\"" : ""}>Approve candidate</button><button class="button button-danger button-small" type="button" data-action="reject-recipe" data-recipe-id="${escapeHTML(candidateId)}">Reject</button></div></article><aside class="panel review-evidence"><p class="eyebrow">VERIFICATION EVIDENCE</p><h3>Tests decide</h3>${evidence.length ? `<ul class="evidence-list">${evidence.map((item) => { const kind = statusKind(item.status); return `<li class="evidence-item"><span class="evidence-mark ${kind === "error" ? "fail" : kind === "warning" ? "pending" : ""}">${kind === "success" ? "✓" : kind === "error" ? "×" : "…"}</span><div><strong>${escapeHTML(item.name)}</strong><small>${escapeHTML(item.detail || String(item.status || "Pending").replace(/_/g, " "))}</small></div></li>`; }).join("")}</ul>` : emptyState("…", "Verification not run", "Run the independent golden and held-out fixture checks before approval.")}<div class="history-list"><p class="eyebrow">VERSION HISTORY</p>${renderVersionHistory(automation)}</div></aside>`;
  }

  function renderVersionHistory(automation) {
    const versions = state.versions.length ? state.versions : listFrom(automation, ["recipe_versions", "versions"]);
    if (!versions.length) return `<span class="table-sub">No version history returned by the API.</span>`;
    return versions.slice(0, 5).map((version) => `<div class="history-row"><span>v${escapeHTML(firstValue(version, ["version_number", "version", "id"], "—"))}</span><strong>${escapeHTML(String(firstValue(version, ["status"], "UNKNOWN")).replace(/_/g, " "))}</strong></div>`).join("");
  }

  function renderRuns() { $("#runs-table").innerHTML = renderRunRows(state.runs); }

  function repairProposals() {
    return state.automations.flatMap((automation) => listFrom(automation, ["repair_proposals", "repairs"]).map((repair) => Object.assign({ automation_id: automation.id, automation_name: firstValue(automation, ["name"], "Automation") }, repair)));
  }

  function renderDrift() {
    const repairs = repairProposals().filter((repair) => !["APPROVED", "REJECTED"].includes(String(repair.status || "").toUpperCase()));
    $("#repair-status-pill").className = `pill ${repairs.length ? "pill-amber" : "pill-neutral"}`;
    $("#repair-status-pill").textContent = repairs.length ? `${repairs.length} awaiting review` : "No open proposals";
    if (!repairs.length) {
      const blockedRun = state.runs.find((run) => statusKind(run.status) === "warning");
      const repairAction = blockedRun && getAutomation(firstValue(blockedRun, ["automation_id"])) ? `<button class="button button-primary button-small" type="button" data-action="request-repair" data-run-id="${escapeHTML(blockedRun.id || blockedRun.run_id || "")}" style="margin-top:14px">Request repair proposal</button>` : "";
      $("#drift-content").innerHTML = emptyState("⌁", "No drift to review", "Blocked inputs and proposed repairs will appear here when an active recipe meets an incompatible file.", repairAction);
      return;
    }
    $("#drift-content").innerHTML = repairs.map((repair) => {
      const report = firstValue(repair, ["drift_report", "drift_report_json", "report"], {}) || {};
      const proposalId = firstValue(repair, ["id", "repair_proposal_id"], "");
      return `<article class="drift-card"><div><p class="eyebrow">${escapeHTML(firstValue(repair, ["automation_name"], "AUTOMATION"))}</p><h3>${escapeHTML(firstValue(repair, ["title", "reason", "error_code"], "Input drift detected"))}</h3><p>${escapeHTML(firstValue(repair, ["message", "description"], typeof report === "string" ? report : firstValue(report, ["message", "reason"], "Execution was blocked before an unverified output could be written.")))}</p></div><div class="drift-detail"><div><span>Input</span><strong>${escapeHTML(firstValue(repair, ["input_reference", "drift_input", "file_reference"], "—"))}</strong></div><div><span>Quarantine</span><strong>${escapeHTML(firstValue(repair, ["quarantine_reference", "quarantined_file"], "Recorded by server"))}</strong></div><div><span>Status</span><strong>${escapeHTML(String(firstValue(repair, ["status"], "PROPOSED")).replace(/_/g, " "))}</strong></div></div><div class="drift-actions"><button class="button button-secondary button-small" type="button" data-action="verify-repair" data-repair-id="${escapeHTML(proposalId)}">Verify</button><button class="button button-primary button-small" type="button" data-action="approve-repair" data-repair-id="${escapeHTML(proposalId)}" ${String(repair.status || "").toUpperCase() !== "VERIFIED" ? "disabled title=\"Full regression suite must pass first\"" : ""}>Approve</button><button class="button button-danger button-small" type="button" data-action="reject-repair" data-repair-id="${escapeHTML(proposalId)}">Reject</button></div></article>`;
    }).join("");
  }

  function renderAll() {
    normalizeRuns();
    renderHealth();
    renderMetrics();
    renderOverviewRuns();
    renderLedger();
    renderAutomations();
    renderRecipeReview();
    renderRuns();
    renderDrift();
  }

  async function loadDashboard() {
    state.loadErrors = [];
    const [health, metrics, automations] = await Promise.allSettled([
      request("/health"),
      request("/metrics"),
      request("/automations")
    ]);
    if (health.status === "fulfilled") state.health = health.value; else state.loadErrors.push("health");
    if (metrics.status === "fulfilled") state.metrics = objectFrom(metrics.value); else state.loadErrors.push("metrics");
    if (automations.status === "fulfilled") state.automations = normalizeAutomations(automations.value); else state.loadErrors.push("automations");
    if (state.selectedAutomationId && !getAutomation()) state.selectedAutomationId = null;
    if (!state.selectedAutomationId && state.automations.length) state.selectedAutomationId = state.automations[0].id;
    $("#last-updated").textContent = `Synced ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    renderAll();
    if (state.loadErrors.length === 3) showToast("The local API is not available yet. Empty states are shown until it starts.", "warning");
  }

  async function loadVersions() {
    const automation = getAutomation();
    if (!automation || !automation.id) return;
    try {
      const payload = await request(`/automations/${encodeURIComponent(automation.id)}/versions`);
      state.versions = listFrom(payload, ["versions", "recipe_versions", "items", "results"]);
    } catch (_) {
      state.versions = [];
    }
    renderAutomationDetail();
    renderRecipeReview();
  }

  async function selectAutomation(id) {
    state.selectedAutomationId = id;
    state.versions = [];
    renderAutomations();
    renderRecipeReview();
    await loadVersions();
  }

  function navigate(section) {
    const target = document.getElementById(section);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.nav === section));
    const titles = { overview: "Overview", automations: "Automations", "recipe-review": "Recipe review", runs: "Runs", drift: "Drift & repair" };
    $("#page-title").textContent = titles[section] || "Overview";
  }

  function openCreate() { $("#create-modal").showModal(); $("#automation-name").focus(); }
  function closeDialog(id) { const dialog = $(id); if (dialog.open) dialog.close(); }

  function openRun() {
    const automation = getAutomation();
    if (!automation) return;
    $("#run-modal-intro").textContent = `Use the active approved recipe for ${firstValue(automation, ["name"], "this automation")}.`;
    $("#run-modal").showModal();
    $("#run-input").focus();
  }

  async function submitCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form).entries());
    try {
      const selectedFile = form.querySelector('input[type="file"]')?.files?.[0];
      if (selectedFile) {
        const upload = new FormData();
        upload.append("file", selectedFile);
        const uploaded = await request("/files/profile", { method: "POST", body: upload });
        body.input_reference = uploaded.path;
        showToast("CSV profiled locally. Creating the automation draft.");
      }
      body.task_description = body.description;
      delete body.file;
      await jsonRequest("/automations", "POST", body);
      closeDialog("#create-modal");
      form.reset();
      showToast("Automation draft created.");
      await loadDashboard();
    } catch (error) { showToast(error.message, "error"); }
  }

  async function submitRun(event) {
    event.preventDefault();
    const automation = getAutomation();
    if (!automation) return;
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      await jsonRequest(`/automations/${encodeURIComponent(automation.id)}/runs`, "POST", body);
      closeDialog("#run-modal");
      event.currentTarget.reset();
      showToast("Run started. Refresh when the result is ready.");
      await loadDashboard();
    } catch (error) { showToast(error.message, "error"); }
  }

  async function postAction(path, message, body = {}) {
    try {
      await jsonRequest(path, "POST", body);
      showToast(message);
      await loadDashboard();
      await loadVersions();
    } catch (error) { showToast(error.message, "error"); }
  }

  async function profileAutomation() {
    const automation = getAutomation();
    if (!automation) return;
    const input = window.prompt("Input CSV reference to profile", firstValue(automation, ["input_reference", "input_path"], ""));
    if (input === null) return;
    try {
      const profile = await jsonRequest(`/automations/${encodeURIComponent(automation.id)}/profile`, "POST", { input_reference: input });
      state.profiles[automation.id] = profile;
      renderAutomationDetail();
      showToast("CSV profiled locally. Review the profile before compiling.");
    } catch (error) { showToast(error.message, "error"); }
  }

  async function generateRecipe() {
    const automation = getAutomation();
    if (!automation) return;
    const model = window.prompt("Local Ollama model tag (leave blank to use the offline fixture recipe)", "gemma3:4b");
    const recipeFile = model ? null : "examples/recipes/expense-v1.json";
    await postAction(`/automations/${encodeURIComponent(automation.id)}/generate-recipe`, "Recipe candidate generated and is ready for review.", { input_reference: firstValue(automation, ["input_reference", "input_path"], null), description: firstValue(automation, ["description", "task_description"], ""), model: model || null, recipe_file: recipeFile });
  }

  async function handleAction(action, element) {
    const automation = getAutomation();
    const id = element.dataset.recipeId;
    const repairId = element.dataset.repairId;
    if (action === "profile") return profileAutomation();
    if (action === "generate") return generateRecipe();
    if (action === "verify-recipe") return postAction(`/recipes/${encodeURIComponent(id)}/verify`, "Recipe verification completed.");
    if (action === "approve-recipe") return postAction(`/recipes/${encodeURIComponent(id)}/approve`, "Recipe approved and activated.");
    if (action === "reject-recipe") return postAction(`/recipes/${encodeURIComponent(id)}/reject`, "Recipe candidate rejected.");
    if (action === "verify-repair") return postAction(`/repair-proposals/${encodeURIComponent(repairId)}/verify`, "Repair regression suite completed.");
    if (action === "approve-repair") return postAction(`/repair-proposals/${encodeURIComponent(repairId)}/approve`, "Verified repair activated.");
    if (action === "reject-repair") return postAction(`/repair-proposals/${encodeURIComponent(repairId)}/reject`, "Repair proposal rejected.");
    if (action === "request-repair" && automation) return postAction(`/automations/${encodeURIComponent(automation.id)}/repair-proposals`, "Repair proposal requested.", { run_id: element.dataset.runId });
  }

  async function inspectRun(id) {
    if (!id) return;
    try {
      const payload = objectFrom(await request(`/runs/${encodeURIComponent(id)}`));
      state.selectedRun = payload;
      const run = payload.run || payload;
      showToast(`${runName(run)} · ${String(firstValue(run, ["status"], "details")).replace(/_/g, " ")}`);
    } catch (error) { showToast(error.message, "error"); }
  }

  document.addEventListener("click", (event) => {
    const nav = event.target.closest("[data-nav]");
    if (nav) {
      event.preventDefault();
      navigate(nav.dataset.nav);
      if (nav.getAttribute("href")) history.replaceState(null, "", nav.getAttribute("href"));
      return;
    }
    if (event.target.closest("[data-open-create]")) return openCreate();
    if (event.target.closest("[data-close-create]")) return closeDialog("#create-modal");
    if (event.target.closest("[data-close-run]")) return closeDialog("#run-modal");
    if (event.target.closest("#refresh-button")) return loadDashboard();
    if (event.target.closest("#run-selected-button")) return openRun();
    const automationCard = event.target.closest("[data-automation-id]");
    if (automationCard) return selectAutomation(automationCard.dataset.automationId);
    const action = event.target.closest("[data-action]");
    if (action) return handleAction(action.dataset.action, action);
    const runRow = event.target.closest("[data-run-id]");
    if (runRow) return inspectRun(runRow.dataset.runId);
  });

  $("#create-form").addEventListener("submit", submitCreate);
  $("#run-form").addEventListener("submit", submitRun);
  window.addEventListener("hashchange", () => navigate(window.location.hash.slice(1) || "overview"));
  navigate(window.location.hash.slice(1) || "overview");
  loadDashboard();
}());
