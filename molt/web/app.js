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
    const model = health.ollama?.status || health.ollama?.configured ? "Model ready" : "Model idle";
    $("#model-chip").innerHTML = `<span class="status-dot"></span>${escapeHTML(model)}`;
    $("#source-dot").className = `live-dot ${online ? "online" : "offline"}`;
    $("#source-note").textContent = online ? "Live from the local API" : "Local API unavailable";
    $("#automation-title").textContent = selected?.name || "No thread selected";
    $("#automation-description").textContent = selected?.description || "Create an automation to start a local thread.";
    $("#automation-count").textContent = String(state.autos.length);
    $("#sync-label").textContent = `Synced ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    $("#api-note").textContent = online ? "Live from the local API" : "Waiting for the local API";
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
    $("#runs-body").innerHTML = state.runs.length ? state.runs.map((run) => `<tr class="${run.status === "BLOCKED_DRIFT" ? "blocked" : ""}"><td><span class="run-name">${escapeHTML(shortId(run.id))}</span><br><small>${formatDate(run.at)}</small></td><td><span class="run-status ${run.status === "BLOCKED_DRIFT" ? "blocked" : status(run.status) === "success" ? "success" : ""}">${escapeHTML(run.status.replace(/_/g, " "))}</span></td><td>${run.rows}</td><td>${run.calls}</td><td>${escapeHTML(shortId(run.ver))}</td><td>${formatMs(run.ms)}</td></tr>`).join("") : `<tr><td class="empty-row" colspan="6">No runs returned by the local API.</td></tr>`;
  }

  function render() {
    const selected = state.autos.find((auto) => String(auto.id) === String(state.selected));
    renderTop(selected); renderRail(); renderMetric(); renderThread(); renderChart(); renderVersions(); renderRuns();
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

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("molt-theme", theme);
    $("#theme-button").textContent = theme === "dark" ? "Light theme" : "Dark theme";
  }

  document.addEventListener("click", (event) => {
    const auto = event.target.closest("[data-auto-id]");
    if (auto) { state.selected = auto.dataset.autoId; load(); return; }
    const actionButton = event.target.closest("[data-action]");
    if (actionButton) { action(actionButton); return; }
    const nodeButton = event.target.closest(".node");
    if (nodeButton) { $("#thread-explanation").innerHTML = `<strong>${escapeHTML(nodeButton.textContent)}</strong> — ${escapeHTML(nodeButton.dataset.explanation)}`; return; }
    if (event.target.closest("#refresh-button")) load();
    if (event.target.closest("#theme-button")) setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });

  const preferred = localStorage.getItem("molt-theme");
  setTheme(preferred || (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  load();
}());
