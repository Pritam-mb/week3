(function () {
  "use strict";

  const state = {
    health: {},
    config: {},
    autos: [],
    runs: [],
    versions: [],
    repairs: [],
    selected: null,
    loading: false,
    temporalRun: null,
    temporalPolls: 0,
    temporalPolling: false,
    temporalTimer: null,
    builder: { sourcePath: "", profile: null, busy: false },
    selectedRun: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const api = (path) => `/api${path}`;
  const L = (value, fallback = "—") => value === undefined || value === null || value === "" ? fallback : String(value);

  function escapeHTML(value) {
    return L(value, "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function list(value, keys = []) {
    if (Array.isArray(value)) return value;
    if (!value || typeof value !== "object") return [];
    for (const key of keys) if (Array.isArray(value[key])) return value[key];
    return Array.isArray(value.data) ? value.data : [];
  }

  function number(value, fallback = 0) {
    const result = Number(value);
    return Number.isFinite(result) ? result : fallback;
  }

  function shortId(value) {
    const text = L(value, "unknown");
    return text.length > 16 ? `…${text.slice(-10)}` : text;
  }

  function formatMs(value) {
    const ms = number(value, NaN);
    if (!Number.isFinite(ms)) return "—";
    return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function status(value) {
    const text = String(value || "").toUpperCase();
    if (["SUCCEEDED", "SUCCESS", "PASS", "PASSED", "ACTIVE", "APPROVED", "ONLINE", "HEALTHY"].includes(text)) return "success";
    if (["BLOCKED_DRIFT", "DRIFT", "QUARANTINED", "PROPOSED", "CANDIDATE", "AWAITING_APPROVAL", "VERIFYING", "PENDING"].includes(text)) return "warning";
    if (["FAILED", "ERROR", "REJECTED", "OFFLINE", "UNAVAILABLE"].includes(text)) return "error";
    return "neutral";
  }

  async function request(path, options = {}) {
    const response = await fetch(api(path), { headers: { Accept: "application/json", ...(options.headers || {}) }, ...options });
    const text = await response.text();
    let payload = {};
    try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = { message: text }; }
    if (!response.ok) throw new Error(payload?.error?.message || payload?.message || `Request failed (${response.status})`);
    return payload;
  }

  function post(path, body = {}) {
    return request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  function mapVersion(version) {
    const recipe = version.recipe || {};
    const verification = version.verification || {};
    const results = list(verification.results, ["checks", "results"]);
    const checks = results.map((item) => [L(item.check || item.fixture || item.name, "verification"), String(item.status || "").toUpperCase() === "PASS"]);
    if (!checks.length && number(verification.checks_total) > 0) checks.push([`${number(verification.checks_passed)} of ${number(verification.checks_total)} checks`, number(verification.checks_failed) === 0]);
    const operations = list(recipe.operations, ["steps"]);
    return {
      id: version.id,
      v: version.version_number || version.version || version.id,
      state: version.status === "ACTIVE" ? "active" : version.status === "REJECTED" ? "rejected" : "candidate",
      kind: version.created_from === "repair" ? "repair" : "compile",
      at: version.created_at,
      calls: number(version.provider_metadata?.llm_calls ?? version.llm_calls, 0),
      steps: operations.map((operation) => L(operation.operation || operation.type || operation.name, "step")).slice(0, 6),
      checks,
      rawStatus: version.status,
    };
  }

  function mapRun(run) {
    return {
      id: run.id || run.run_id,
      status: String(run.status || "UNKNOWN").toUpperCase(),
      rows: number(run.rows_written ?? run.output_rows ?? run.rows_read, 0),
      calls: number(run.llm_calls ?? run.model_calls, 0),
      ver: run.recipe_version_id || run.version_id || run.recipe_version,
      ms: run.duration_ms ?? run.latency_ms,
      at: run.started_at || run.created_at,
      input: run.input,
      output: run.output,
      errorCode: run.error_code,
      errorMessage: run.error_message,
      errorDetails: run.error_details || {},
      quarantine: run.quarantine_artifact_id || run.quarantine,
    };
  }

  async function fromApi() {
    const [health, config, automations] = await Promise.all([
      request("/health"),
      request("/config"),
      request("/automations"),
    ]);
    const rawAutos = list(automations, ["automations", "items", "results"]);
    const autos = rawAutos.map((item) => ({
      id: item.id,
      name: L(item.name, "Untitled thread"),
      ver: item.active_version?.version_number || item.active_version_id || "—",
      description: L(item.description, "A local verified automation thread."),
      status: L(item.status, "DRAFT"),
      inputReference: item.input_reference || "",
    }));
    const selected = autos.find((item) => String(item.id) === String(state.selected)) || autos[0] || null;
    let detail = selected ? await request(`/automations/${encodeURIComponent(selected.id)}`) : {};
    if (selected) {
      await Promise.allSettled([
        request(`/automations/${encodeURIComponent(selected.id)}/runs`).then((value) => { detail.runs = value.runs || value; }),
        request(`/automations/${encodeURIComponent(selected.id)}/versions`).then((value) => { detail.versions = value.versions || value; }),
      ]);
    }
    state.health = health || {};
    state.config = config || {};
    state.autos = autos;
    state.selected = selected?.id || null;
    state.runs = list(detail.runs).map(mapRun).sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0));
    state.versions = list(detail.versions).map(mapVersion);
    state.repairs = list(detail.repair_proposals);
    state.builder.sourcePath = state.builder.sourcePath || selected?.inputReference || "";
    return { selected, detail };
  }

  function showToast(message, kind = "ok") {
    const toast = document.createElement("div");
    toast.className = `toast ${kind === "error" ? "error" : kind === "warn" ? "warn" : ""}`;
    toast.textContent = message;
    $("#toast-region").appendChild(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  function renderTop(selected) {
    const health = state.health || {};
    const online = String(health.status || "").toLowerCase() === "ok";
    const healthChip = $("#health-chip");
    healthChip.className = `status-chip ${online ? "online" : "offline"}`;
    healthChip.innerHTML = `<span class="status-dot"></span>${online ? "API online" : "API unavailable"}`;
    const model = health.ollama?.status === "ready" ? "Model ready" : "Model unavailable";
    $("#model-chip").innerHTML = `<span class="status-dot"></span>${escapeHTML(model)}`;
    $("#source-dot").className = `live-dot ${online ? "online" : "offline"}`;
    $("#source-note").textContent = online ? "Live from the local API" : "Local API unavailable";
    $("#automation-title").textContent = selected?.name || "No thread selected";
    $("#automation-description").textContent = selected?.description || "Create an automation to start a local thread.";
    $("#automation-count").textContent = String(state.autos.length);
    $("#sync-label").textContent = `Synced ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    $("#api-note").textContent = online ? "Live from the local API" : "Waiting for the local API";
    const temporalReady = Boolean(selected?.id && state.config?.temporal && state.versions.some((version) => version.rawStatus === "ACTIVE"));
    $("#temporal-run-button").disabled = !temporalReady;
    renderTemporalStatus();
  }

  function selectedAutomation() {
    return state.autos.find((auto) => String(auto.id) === String(state.selected)) || null;
  }

  function builderValue(id) {
    return $(`#${id}`)?.value?.trim() || "";
  }

  function setBuilderStatus(message, kind = "") {
    const target = $("#builder-status");
    if (!target) return;
    target.className = `builder-status ${kind}`;
    target.textContent = message;
  }

  function renderBuilder() {
    const selected = selectedAutomation();
    const source = state.builder.sourcePath || selected?.inputReference || "";
    const hasAutomation = Boolean(selected);
    const hasSource = Boolean(source);
    const hasProfile = Boolean(state.builder.profile);
    const pathInput = $("#builder-path");
    if (pathInput && document.activeElement !== pathInput) pathInput.value = source;
    const profileButton = $("#profile-input-button");
    const compileButton = $("#compile-recipe-button");
    const stage = $("#builder-stage");
    if (profileButton) profileButton.disabled = !hasAutomation || !hasSource || state.builder.busy;
    if (compileButton) compileButton.disabled = !hasAutomation || !hasSource || state.builder.busy;
    if (stage) stage.textContent = !hasAutomation ? "Step 1 of 4" : !hasProfile ? "Step 2 of 4" : state.versions.some((version) => version.state === "candidate") ? "Step 4 of 4" : "Step 3 of 4";
    const profile = $("#profile-summary");
    if (profile) {
      profile.hidden = !state.builder.profile;
      if (state.builder.profile) {
        const columns = state.builder.profile.columns || [];
        profile.innerHTML = `<strong>Profile ready</strong> · ${number(state.builder.profile.row_count)} rows · ${columns.length} columns · ${escapeHTML(columns.join(", "))}`;
      }
    }
    const sourceMode = $("#builder-source")?.value || "gemma";
    const modelField = $("#builder-model-field");
    if (modelField) modelField.style.display = sourceMode === "gemma" ? "grid" : "none";
  }

  function renderRail() {
    $("#automation-rail").innerHTML = state.autos.length ? state.autos.map((auto) => {
      const selected = String(auto.id) === String(state.selected);
      const kind = auto.status === "ACTIVE" ? "ok" : auto.status === "DRAFT" ? "" : "warn";
      return `<button class="rail-item ${selected ? "selected" : ""}" type="button" data-auto-id="${escapeHTML(auto.id)}"><strong>${escapeHTML(auto.name)}</strong><small class="rail-status ${kind}">${escapeHTML(auto.status.replace(/_/g, " "))} · v${escapeHTML(auto.ver)}</small></button>`;
    }).join("") : `<div class="rail-item"><strong>No threads yet</strong><small>Create one through the local API.</small></div>`;
  }

  function renderMetric() {
    const calls = state.runs.reduce((sum, run) => sum + run.calls, 0);
    const blocked = state.runs.filter((run) => run.status === "BLOCKED_DRIFT").length;
    const succeeded = state.runs.filter((run) => run.status === "SUCCEEDED").length;
    $("#calls-number").textContent = String(calls);
    $("#calls-caption").textContent = `${succeeded} successful run${succeeded === 1 ? "" : "s"} · ${blocked} drift block${blocked === 1 ? "" : "s"} · ${state.runs.length} total runs`;
  }

  function node(label, tone, explanation, model = false) {
    return `<button class="node ${tone} ${model ? "model" : ""}" type="button" aria-label="${escapeHTML(label)}" data-explanation="${escapeHTML(explanation)}">${escapeHTML(label)}</button>`;
  }

  function renderThread() {
    const blocked = state.runs.some((run) => run.status === "BLOCKED_DRIFT");
    const candidate = state.versions.some((version) => version.state === "candidate");
    $("#thread-canvas").innerHTML = `<div class="thread-lanes">
      <div class="lane hot"><span class="lane-label">Build</span><div class="lane-track"><span class="bead"></span>${node("Profile input", "ok", "The local API profiles the input contract before recipe generation.")}<span class="bead"></span>${node("Compile recipe", "ok", "The local model may propose a constrained recipe here.", true)}${node("Verify checks", candidate ? "warn" : "ok", candidate ? "A candidate is waiting for independent checks." : "Independent examples and invariants decide whether the recipe can proceed.")}${node("Approve", "ok", "Approval activates the verified recipe; it is not implied by model output.")}</div></div>
      <div class="lane ${blocked ? "blocked" : "hot"}"><span class="lane-label">Run</span><div class="lane-track"><span class="bead"></span>${node("Approved recipe", "ok", "The active version is reused without another model call.")}${node("Execute rows", blocked ? "bad blocked" : "ok", blocked ? "Input drift cuts the thread before an unverified output is written." : "The deterministic executor applies the approved recipe.")}${node("Reuse", "ok", "Compatible runs stay on the deterministic path.")}</div></div>
      <div class="lane repair"><span class="lane-label">Repair</span><div class="lane-track"><span class="bead"></span>${node("Drift blocked", blocked ? "bad blocked" : "warn", blocked ? "A drifted input is quarantined and remains visible in run history." : "The repair lane opens only when drift is detected.")}${node("Repair proposal", "warn", "Repair is a second model boundary or a manual candidate; it remains inactive until verified.", true)}${node("Verified repair", "ok", "A repair ties back to the active thread only after regression checks pass.")}</div></div>
    </div>`;
    $("#thread-explanation").textContent = "Select a bead to inspect its role.";
  }

  function renderJourney(selected) {
    const active = state.versions.some((version) => version.state === "active");
    const candidate = state.versions.some((version) => version.state === "candidate");
    const blocked = state.runs.some((run) => run.status === "BLOCKED_DRIFT");
    const latest = state.runs[0];
    const steps = [
      ["01", "Profile input", "Schema + masked samples", true],
      ["02", "Compile recipe", "Gemma proposes JSON", candidate || active],
      ["03", "Verify + approve", candidate ? "Candidate needs review" : active ? "Active version" : "Tests decide", active ? true : candidate],
      ["04", "Run deterministically", latest ? `${latest.calls} model calls` : "Zero calls after approval", latest?.status === "SUCCEEDED" || active],
      ["05", blocked ? "Drift blocked" : "Repair if needed", blocked ? "Quarantine; never guess" : "Only after a mismatch", blocked ? "blocked" : true],
    ];
    $("#journey-graph").innerHTML = steps.map(([numberValue, title, detail, tone]) => `<div class="journey-step ${tone === "blocked" ? "blocked" : tone ? "active" : ""}"><span class="journey-icon">${tone === "blocked" ? "×" : tone ? "✓" : numberValue}</span><strong>${escapeHTML(title)}</strong><small>${escapeHTML(detail)}</small></div>`).join("");
    $("#journey-caption").textContent = selected ? `${selected.name} · ${blocked ? "latest file was blocked" : active ? "approved recipe ready" : "start by creating a recipe"}` : "Create an automation to begin";
  }

  function safeFileName(value) {
    return L(value, "workspace file").split(/[\\/]/).pop();
  }

  function detailList(value) {
    if (!Array.isArray(value) || !value.length) return "";
    return `<ul class="inspector-list">${value.slice(0, 12).map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>`;
  }

  function renderRunInspector() {
    const panel = $("#run-inspector");
    if (!panel) return;
    const run = state.runs.find((item) => String(item.id) === String(state.selectedRun));
    if (!run) { panel.hidden = true; panel.innerHTML = ""; return; }
    panel.hidden = false;
    const blocked = run.status === "BLOCKED_DRIFT";
    const details = run.errorDetails || {};
    const structural = [
      details.missing ? `<strong>Missing columns:</strong>${detailList(details.missing)}` : "",
      details.extra ? `<strong>Unexpected columns:</strong>${detailList(details.extra)}` : "",
      details.expected ? `<strong>Expected contract:</strong>${detailList(details.expected)}` : "",
      details.observed ? `<strong>Observed structure:</strong>${detailList(details.observed)}` : "",
      details.column ? `<strong>Affected column:</strong> ${escapeHTML(details.column)}` : "",
      details.unmapped_count ? `<strong>Unmapped rows:</strong> ${escapeHTML(details.unmapped_count)}` : "",
    ].filter(Boolean).join("");
    panel.innerHTML = `<div class="inspector-top"><div><h3 class="inspector-title">${blocked ? "Why Molt blocked this file" : "What Molt did with this file"}</h3><p class="inspector-subtitle">${escapeHTML(safeFileName(run.input))} · ${formatDate(run.at)}</p></div><span class="run-status ${blocked ? "blocked" : "success"}">${escapeHTML(run.status.replace(/_/g, " "))}</span></div><div class="inspector-grid"><div class="inspector-stat"><strong>${escapeHTML(run.errorCode || (run.status === "SUCCEEDED" ? "RECIPE_APPLIED" : "RUN_RESULT"))}</strong><span>decision</span></div><div class="inspector-stat"><strong>${run.rows} rows</strong><span>rows written / observed</span></div><div class="inspector-stat"><strong>${run.calls} model calls</strong><span>at execution time</span></div></div><div class="inspector-details">${blocked ? `<p><strong>Molt did not guess.</strong> The input no longer satisfied the approved recipe contract, so no output was written and the file was quarantined for review.</p><p>${escapeHTML(run.errorMessage || "The file was rejected by the deterministic guard.")}</p>${structural}` : `<p><strong>Compatible input.</strong> The stored approved recipe ran deterministically. The model was not called again.</p><p>Output: <code>${escapeHTML(safeFileName(run.output))}</code></p>`}</div>`;
  }

  function renderChart() {
    const runs = state.runs.slice(0, 10).reverse();
    const width = 640; const height = 170; const pad = 24;
    const max = Math.max(1, runs.length);
    const x = (index) => pad + (index * (width - pad * 2)) / Math.max(1, max - 1);
    const baseline = runs.map((_, index) => `${x(index)},${height - pad - (index * (height - pad * 2)) / Math.max(1, max - 1)}`).join(" ");
    let step = "";
    runs.forEach((run, index) => { const px = x(index); const py = height - pad - (run.calls ? 35 : 0); step += index ? ` L${px} ${py} L${px} ${py}` : `M${px} ${py}`; });
    const points = runs.map((run, index) => `<circle cx="${x(index)}" cy="${height - pad - (run.calls ? 35 : 0)}" r="3" fill="var(--ok)"></circle>`).join("");
    $("#calls-chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="var(--line)"/><polyline points="${baseline}" fill="none" stroke="var(--strong-line)" stroke-width="1.5" stroke-dasharray="4 5"/><path d="${step || `M${pad} ${height - pad}`}" fill="none" stroke="var(--ok)" stroke-width="2"/>${points}<text x="${pad}" y="${height - 7}" fill="var(--faint)" font-size="9">older</text><text x="${width - pad - 24}" y="${height - 7}" fill="var(--faint)" font-size="9">latest</text></svg>`;
    $("#run-summary").textContent = `${state.runs.length} run${state.runs.length === 1 ? "" : "s"}`;
  }

  function repairFor(versionId) { return state.repairs.find((repair) => String(repair.candidate_version_id) === String(versionId)); }

  function renderVersions() {
    $("#version-summary").textContent = `${state.versions.length} version${state.versions.length === 1 ? "" : "s"}`;
    if (!state.versions.length) { $("#versions-list").innerHTML = `<p class="empty-row">No recipe versions returned by the local API.</p>`; return; }
    $("#versions-list").innerHTML = state.versions.slice(0, 5).map((version) => {
      const repair = repairFor(version.id);
      const actions = version.state === "candidate" ? `<div class="version-actions"><button class="mini-button" data-action="verify" data-id="${escapeHTML(repair ? repair.id : version.id)}" data-kind="${repair ? "repair" : "compile"}">Run tests</button><button class="mini-button primary" data-action="approve" data-id="${escapeHTML(repair ? repair.id : version.id)}" data-kind="${repair ? "repair" : "compile"}" ${version.checks.some((check) => !check[1]) ? "disabled" : ""}>Approve</button></div>` : "";
      const checks = version.checks.length ? `<div class="version-checks">${version.checks.slice(0, 5).map((check) => `<span class="check ${check[1] ? "pass" : "fail"}">${check[1] ? "pass" : "fail"} · ${escapeHTML(check[0])}</span>`).join("")}</div>` : "";
      const steps = version.steps.length ? version.steps.map((step, index) => `${index ? '<span class="step-thread"></span>' : ""}<span class="step-chip">${escapeHTML(step)}</span>`).join("") : `<span class="step-chip">constrained recipe</span>`;
      return `<article class="version-card"><div class="version-top"><span class="version-id">v${escapeHTML(version.v)} · ${escapeHTML(version.kind)}</span><span class="state ${version.state}">${escapeHTML(version.state)}</span></div><div class="version-steps">${steps}</div><div class="version-meta"><span>${formatDate(version.at)} · ${version.calls} model call${version.calls === 1 ? "" : "s"}</span><span>${escapeHTML(version.rawStatus)}</span></div>${checks}${actions}</article>`;
    }).join("");
  }

  function renderRuns() {
    $("#runs-body").innerHTML = state.runs.length ? state.runs.map((run) => `<tr class="${run.status === "BLOCKED_DRIFT" ? "blocked" : ""}" data-run-id="${escapeHTML(run.id)}" tabindex="0" title="Select to inspect this run"><td><span class="run-name">${escapeHTML(shortId(run.id))}</span><br><small>${formatDate(run.at)}</small></td><td><span class="run-status ${run.status === "BLOCKED_DRIFT" ? "blocked" : status(run.status) === "success" ? "success" : ""}">${escapeHTML(run.status.replace(/_/g, " "))}</span></td><td>${run.rows}</td><td>${run.calls}</td><td>${escapeHTML(shortId(run.ver))}</td><td>${formatMs(run.ms)}</td></tr>`).join("") : `<tr><td class="empty-row" colspan="6">No runs returned by the local API.</td></tr>`;
  }

  function render() {
    const selected = state.autos.find((auto) => String(auto.id) === String(state.selected));
    renderTop(selected); renderRail(); renderBuilder(); renderMetric(); renderThread(); renderJourney(selected); renderChart(); renderVersions(); renderRuns(); renderRunInspector();
  }

  async function load() {
    if (state.loading) return;
    state.loading = true;
    try { await fromApi(); render(); } catch (error) { showToast(error.message, "error"); render(); } finally { state.loading = false; }
  }

  async function action(element) {
    const kind = element.dataset.kind;
    const id = encodeURIComponent(element.dataset.id);
    const operation = element.dataset.action;
    const route = kind === "repair" ? `/repair-proposals/${id}/${operation}` : `/recipes/${id}/${operation}`;
    try { await post(route); showToast(`${operation === "verify" ? "Verification" : "Approval"} completed.`); await load(); } catch (error) { showToast(error.message, "error"); }
  }

  async function uploadBuilderInput() {
    const file = $("#builder-file")?.files?.[0];
    if (!file) return builderValue("builder-path");
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(api("/files/profile"), { method: "POST", body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "CSV upload failed");
    state.builder.sourcePath = payload.path;
    state.builder.profile = payload.profile;
    return payload.path;
  }

  async function createAutomationFromBuilder() {
    if (state.builder.busy) return;
    const name = builderValue("builder-name");
    const task = builderValue("builder-task");
    const typedPath = builderValue("builder-path");
    if (!name || !task) { setBuilderStatus("Enter a workflow name and task first.", "warn"); return; }
    state.builder.busy = true; renderBuilder(); setBuilderStatus("Uploading and creating the workflow…");
    try {
      const sourcePath = (await uploadBuilderInput()) || typedPath;
      if (!sourcePath) throw new Error("Choose a CSV file or enter a workspace CSV path.");
      const created = await post("/automations", { name, description: task, input_reference: sourcePath });
      state.selected = created.id;
      state.builder.sourcePath = sourcePath;
      state.builder.profile = null;
      setBuilderStatus(`Created ${created.name}. Next, profile the input, then compile a recipe.`, "success");
      await load();
    } catch (error) { setBuilderStatus(error.message, "error"); showToast(error.message, "error"); }
    finally { state.builder.busy = false; renderBuilder(); }
  }

  async function profileBuilderInput() {
    const selected = selectedAutomation();
    const sourcePath = state.builder.sourcePath || builderValue("builder-path");
    if (!selected || !sourcePath) { setBuilderStatus("Create a workflow and choose its CSV first.", "warn"); return; }
    state.builder.busy = true; renderBuilder(); setBuilderStatus("Profiling the CSV without sending raw rows to the model…");
    try {
      const result = await post(`/automations/${encodeURIComponent(selected.id)}/profile`, { input_reference: sourcePath });
      state.builder.sourcePath = sourcePath; state.builder.profile = result;
      setBuilderStatus("Profile complete. The next step is compiling a constrained recipe.", "success");
    } catch (error) { setBuilderStatus(error.message, "error"); showToast(error.message, "error"); }
    finally { state.builder.busy = false; renderBuilder(); }
  }

  async function compileBuilderRecipe() {
    const selected = selectedAutomation();
    const sourcePath = state.builder.sourcePath || builderValue("builder-path");
    const task = builderValue("builder-task") || selected?.description;
    if (!selected || !sourcePath || !task) { setBuilderStatus("Create the workflow, choose a CSV, and enter a task first.", "warn"); return; }
    state.builder.busy = true; renderBuilder();
    const source = $("#builder-source")?.value || "gemma";
    setBuilderStatus(source === "gemma" ? "Gemma is proposing a recipe. Molt will validate and test it before approval…" : "Loading the checked recipe. You still must run tests and approve it…");
    try {
      const body = { input_reference: sourcePath, task };
      if (source === "gemma") body.model = builderValue("builder-model") || "gemma3:4b";
      else body.recipe_file = "examples/recipes/expense-v1.json";
      const candidate = await post(`/automations/${encodeURIComponent(selected.id)}/compile`, body);
      setBuilderStatus(`Candidate ${shortId(candidate.id)} created. Review its checks below; approval is still explicit.`, candidate.status === "AWAITING_APPROVAL" ? "success" : "warn");
      await load();
    } catch (error) { setBuilderStatus(error.message, "error"); showToast(error.message, "error"); }
    finally { state.builder.busy = false; renderBuilder(); }
  }

  async function startTemporalRun() {
    const selected = state.autos.find((auto) => String(auto.id) === String(state.selected));
    if (!selected) return;
    const input = window.prompt("Workspace CSV reference for the durable run", "in/input.csv");
    if (!input) return;
    try {
      const result = await post(`/automations/${encodeURIComponent(selected.id)}/temporal-runs`, {
        input_reference: input,
        wait: false,
      });
      state.temporalRun = { workflow_id: result.workflow_id, automation_id: selected.id, status: "RUNNING" };
      localStorage.setItem("molt-temporal-run", JSON.stringify(state.temporalRun));
      state.temporalPolls = 0;
      renderTemporalStatus();
      pollTemporalRun();
      showToast(`Temporal workflow started: ${shortId(result.workflow_id)}`);
    } catch (error) { showToast(error.message, "error"); }
  }

  function renderTemporalStatus() {
    const run = state.temporalRun;
    if (!run) return;
    const outcome = run.result?.status;
    $("#temporal-status").textContent = `Durable run ${shortId(run.workflow_id)}: ${run.status}${outcome ? ` · Molt ${outcome}` : ""}${run.notice ? ` · ${run.notice}` : ""}`;
  }

  async function pollTemporalRun() {
    if (!state.temporalRun || state.temporalPolling) return;
    window.clearTimeout(state.temporalTimer);
    state.temporalPolling = true;
    const run = state.temporalRun;
    try {
      const result = await request(`/temporal-runs/${encodeURIComponent(run.workflow_id)}`);
      if (run !== state.temporalRun) return;
      const changed = run.status !== result.status;
      Object.assign(run, result, { notice: "" });
      if (changed && result.status !== "RUNNING") await load();
    } catch (_) {
      run.notice = "Status unavailable; retrying. This does not mean the workflow failed.";
    } finally {
      state.temporalPolling = false;
      state.temporalPolls += 1;
      if ((state.temporalRun?.status === "RUNNING" || state.temporalRun?.notice) && state.temporalPolls < 100) {
        state.temporalTimer = window.setTimeout(pollTemporalRun, 3000);
      } else if (state.temporalPolls >= 100) {
        state.temporalRun.notice = "Automatic checks paused. Refresh to check again.";
      }
      renderTemporalStatus();
    }
  }

  async function runCsv(pathOrFile) {
    const selected = state.autos.find((auto) => String(auto.id) === String(state.selected));
    if (!selected) { showToast("No automation selected", "warn"); return; }
    const resultBox = $("#run-result-box");
    if (resultBox) {
      resultBox.style.display = "block";
      resultBox.className = "run-result-box";
      resultBox.innerHTML = "Running active recipe on CSV...";
    }
    try {
      let targetPath = pathOrFile;
      if (typeof pathOrFile !== "string" && pathOrFile && typeof pathOrFile === "object" && "name" in pathOrFile) {
        const formData = new FormData();
        formData.append("file", pathOrFile);
        const uploadRes = await fetch(api("/files/profile"), { method: "POST", body: formData });
        const uploadData = await uploadRes.json();
        if (!uploadRes.ok) throw new Error(uploadData?.error?.message || "Upload failed");
        targetPath = uploadData.path;
      }
      const record = await post(`/automations/${encodeURIComponent(selected.id)}/runs`, { path: targetPath });
      const succeeded = record.status === "SUCCEEDED";
      if (resultBox) {
        resultBox.className = `run-result-box ${succeeded ? "success" : "drift"}`;
        resultBox.innerHTML = succeeded
          ? `<strong>✓ Run Succeeded!</strong><br>Processed ${record.rows_read} rows in ${record.duration_ms} ms with <strong>0 model calls</strong>.<br><small>Output written to: ${escapeHTML(shortId(record.output))}</small>`
          : `<strong>⚠ Drift Blocked & Quarantined!</strong><br>Code: <code>${escapeHTML(record.error_code)}</code> — ${escapeHTML(record.error_message)}<br><small>Zero outputs written. Quarantined for review.</small>`;
      }
      showToast(succeeded ? "Run succeeded (0 model calls)" : "Drift blocked and quarantined", succeeded ? "ok" : "warn");
      await load();
    } catch (err) {
      if (resultBox) {
        resultBox.className = "run-result-box drift";
        resultBox.innerHTML = `<strong>Execution error:</strong> ${escapeHTML(err.message)}`;
      }
      showToast(err.message, "error");
    }
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("molt-theme", theme);
    $("#theme-button").textContent = theme === "dark" ? "Light theme" : "Dark theme";
  }

  document.addEventListener("click", (event) => {
    const auto = event.target.closest("[data-auto-id]");
    if (auto) { state.selected = auto.dataset.autoId; load(); return; }
    const runRow = event.target.closest("[data-run-id]");
    if (runRow) { state.selectedRun = runRow.dataset.runId; renderRunInspector(); window.location.href = `/diff.html?run=${encodeURIComponent(state.selectedRun)}`; return; }
    const actionButton = event.target.closest("[data-action]");
    if (actionButton) { action(actionButton); return; }
    const chip = event.target.closest("[data-run-path]");
    if (chip) { runCsv(chip.dataset.runPath); return; }
    const nodeButton = event.target.closest(".node");
    if (nodeButton) { $("#thread-explanation").innerHTML = `<strong>${escapeHTML(nodeButton.textContent)}</strong> — ${escapeHTML(nodeButton.dataset.explanation)}`; return; }
    if (event.target.closest("#refresh-button")) { load(); state.temporalPolls = 0; pollTemporalRun(); }
    if (event.target.closest("#run-csv-button") || event.target.closest("#csv-dropzone")) {
      const picker = $("#csv-file-picker");
      if (picker && typeof picker.click === "function") picker.click();
      return;
    }
    if (event.target.closest("#temporal-run-button")) return startTemporalRun();
    if (event.target.closest("#create-automation-button")) return createAutomationFromBuilder();
    if (event.target.closest("#profile-input-button")) return profileBuilderInput();
    if (event.target.closest("#compile-recipe-button")) return compileBuilderRecipe();
    if (event.target.closest("#theme-button")) setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });

  const filePicker = $("#csv-file-picker");
  filePicker?.addEventListener?.("change", (e) => {
    const file = e.target?.files?.[0];
    if (file) runCsv(file);
    if (filePicker) filePicker.value = "";
  });

  const dropzone = $("#csv-dropzone");
  dropzone?.addEventListener?.("dragover", (e) => { e.preventDefault?.(); dropzone.classList?.add("dragover"); });
  dropzone?.addEventListener?.("dragleave", () => dropzone.classList?.remove("dragover"));
  dropzone?.addEventListener?.("drop", (e) => {
    e.preventDefault?.();
    dropzone.classList?.remove("dragover");
    const file = e.dataTransfer?.files?.[0];
    if (file) runCsv(file);
  });

  $("#builder-source")?.addEventListener?.("change", renderBuilder);
  $("#builder-file")?.addEventListener?.("change", (event) => {
    const file = event.target?.files?.[0];
    if (file) { $("#builder-path").value = `upload: ${file.name}`; setBuilderStatus(`${file.name} is ready to upload when you create the workflow.`); }
  });

  const preferred = localStorage.getItem("molt-theme");
  try {
    const remembered = JSON.parse(localStorage.getItem("molt-temporal-run"));
    if (typeof remembered?.workflow_id === "string") state.temporalRun = remembered;
  } catch (_) { /* An invalid local preference must not prevent dashboard startup. */ }
  setTheme(preferred || (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  load();
  pollTemporalRun();
}());
