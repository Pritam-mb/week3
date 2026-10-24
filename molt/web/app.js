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
      recipe,
      description: recipe.description || "",
      provider: version.provider_metadata?.provider || version.model_name || "stored recipe",
      verification,
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
      duration: number(run.duration_ms ?? run.latency_ms, 0),
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
    const total = state.runs.length;
    const callsNum = $("#calls-number");
    if (callsNum) callsNum.textContent = String(calls);
    const callsCap = $("#calls-caption");
    if (callsCap) callsCap.textContent = `${succeeded} successful run${succeeded === 1 ? "" : "s"} · ${blocked} drift block${blocked === 1 ? "" : "s"} · ${total} total runs`;

    const bentoSuccess = $("#bento-successful-runs");
    if (bentoSuccess) bentoSuccess.textContent = total ? String(succeeded) : "Not measured";
    const bentoDrift = $("#bento-drift-events");
    if (bentoDrift) bentoDrift.textContent = total ? String(blocked) : "Not measured";
    const bentoAvoided = $("#bento-calls-avoided");
    if (bentoAvoided) bentoAvoided.textContent = total ? String(state.runs.filter((run) => run.status === "SUCCEEDED" && run.calls === 0).length) : "Not measured";
    const bentoLatency = $("#bento-latency");
    if (bentoLatency) {
      const measured = state.runs.filter((run) => run.status === "SUCCEEDED" && run.duration > 0);
      bentoLatency.textContent = measured.length ? `${Math.round(measured.reduce((sum, run) => sum + run.duration, 0) / measured.length)} ms` : "Not measured";
    }
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
    const repairPending = state.repairs.some((repair) => ["PROPOSED", "VERIFIED"].includes(repair.status));
    const steps = [
      ["Profile input", "The CSV is inspected for columns, types, row count, and fingerprints. Raw rows are not sent to the model.", active || candidate, "Done", "Compile can use the structural profile."],
      ["Compile recipe", "Gemma proposes constrained JSON operations. It does not write Python or change the CSV.", candidate || active, candidate ? "Candidate" : active ? "Completed" : "Waiting", "The candidate must pass independent tests."],
      ["Verify recipe", candidate ? "The candidate is tested against golden outputs, errors, and invariants." : active ? "The active recipe already passed its regression suite." : "No candidate has been created yet.", candidate ? "Review" : active ? "Passed" : "Waiting", "A failed candidate stays inactive."],
      ["Human approval", active ? "A person approved the verified recipe, so it is the active version." : "A person reviews the recipe and explicitly approves it after tests pass.", active ? "Approved" : candidate ? "Action needed" : "Waiting", "Only an approved recipe can run."],
      ["Run deterministically", latest ? `${latest.calls} model calls were recorded during this run.` : "The approved recipe is reused without another model call.", latest ? "Recorded" : "Waiting", "Compatible input produces an atomic output."],
      ["Drift blocked", blocked ? "The input no longer matches the approved contract. No output is written and the file is quarantined." : "This step appears only when a file changes in an unapproved way.", blocked ? "Blocked" : "Not triggered", "Select the blocked run to open the repair path."],
      ["Mastra repair proposal", repairPending ? "Mastra returned a candidate, but it is not active." : "Only request this after a blocked run. Mastra suggests; Molt still decides.", repairPending ? "Candidate stored" : blocked ? "Ready" : "Waiting", "Next: run the full regression suite."],
    ];
    $("#journey-graph").innerHTML = steps.map(([title, detail, done, statusText, next], index) => `<button class="lifecycle-step ${statusText === "Blocked" ? "blocked" : done ? "done" : ""}" type="button" aria-expanded="false"><span class="lifecycle-dot"></span><strong>${escapeHTML(title)}</strong><span class="lifecycle-status">${escapeHTML(statusText)}</span><span class="lifecycle-evidence"><span class="lifecycle-detail"><b>What happens</b><span>${escapeHTML(detail)}</span></span><span class="lifecycle-detail"><b>Result</b><span>${escapeHTML(statusText)}</span></span><span class="lifecycle-detail"><b>What happens next</b><span>${escapeHTML(next)}</span></span></span></button>`).join("");
    $("#journey-caption").textContent = selected ? `${selected.name} · ${blocked ? "latest file was blocked" : active ? "approved recipe ready" : "start by creating a recipe"}` : "Create an automation to begin";
  }

  function renderBeads() {
    const target = $("#run-beads");
    if (!target) return;
    if (!state.runs.length) { target.innerHTML = `<span class="empty-state">No runs yet.</span>`; $("#result-sentence").textContent = "No runs yet. Run a compatible CSV to create evidence."; return; }
    const activeVersion = state.versions.find((version) => version.state === "active");
    target.innerHTML = `${activeVersion ? `<div class="version-divider">v${escapeHTML(activeVersion.v)} active</div>` : ""}${state.runs.map((run, index) => `<button class="run-bead ${run.status === "BLOCKED_DRIFT" ? "blocked" : ""}" type="button" data-run-id="${escapeHTML(run.id)}" aria-label="${escapeHTML(run.status)} run ${index + 1}"><i></i><span>run ${index + 1}</span></button>`).join("")}`;
    const latest = state.runs[0];
    $("#result-sentence").textContent = latest.status === "BLOCKED_DRIFT" ? "Latest result: input drift was detected before output was written." : "Latest result: compatible input reused the approved recipe with no model call during execution.";
  }

  function renderRoles() {
    const health = state.health || {};
    const roles = [
      ["Gemma (Ollama)", "compiler", health.ollama?.status === "ready", "gold", health.ollama?.status === "ready" ? "ready" : "unavailable"],
      ["Mastra sidecar", "repair agent", health.mastra?.status === "ready", "gold", health.mastra?.status === "ready" ? "ready" : "unavailable"],
      ["Molt verifier", "authority", true, "jade", "ready"],
      ["Temporal", "durable run", Boolean(state.config?.temporal), "", "configured"],
      ["TabPFN", "advisory", Boolean(health.tabpfn?.enabled && health.tabpfn?.license_accepted), "", health.tabpfn?.enabled ? "unavailable" : "disabled"],
    ];
    $("#roles-list").innerHTML = roles.map(([name, role, ready, tone, statusText]) => `<div class="role-row"><span class="role-status ${ready ? "ready" : statusText === "disabled" ? "disabled" : ""}" aria-label="${statusText}"></span><span class="role-name">${escapeHTML(name)}</span><span class="role-pill ${tone}">${escapeHTML(role)}</span><span class="role-state">${escapeHTML(statusText)}</span></div>`).join("");
  }

  function renderRepairCard() {
    const target = $("#repair-card");
    const run = state.runs.find((item) => String(item.id) === String(state.selectedRun));
    if (!target || !run || run.status !== "BLOCKED_DRIFT") { if (target) { target.hidden = true; target.innerHTML = ""; } return; }
    const proposal = state.repairs.find((item) => String(item.source_run_id) === String(run.id));
    const mastraReady = state.health?.mastra?.status === "ready";
    const statusText = proposal?.status || "not requested";
    const proposalStatus = proposal?.status || "NOT_REQUESTED";
    const steps = [
      ["1. Drift blocked", "Molt stopped before writing output and placed the input in quarantine.", true],
      ["2. Ask Mastra", "Mastra receives only the active recipe, masked profile, and structural drift report.", Boolean(proposal) || mastraReady],
      ["3. Candidate stored", proposal ? "The proposed recipe is stored separately from the active recipe." : "Nothing is stored until Mastra returns a valid candidate.", Boolean(proposal)],
      ["4. Run tests", proposalStatus === "VERIFIED" ? "The complete regression suite passed." : proposalStatus === "REJECTED" ? "The regression suite rejected this candidate." : "Click Run tests on the candidate before approval.", ["VERIFIED", "REJECTED"].includes(proposalStatus)],
      ["5. Human decision", proposalStatus === "APPROVED" ? "A person approved the verified repair." : proposalStatus === "REJECTED" ? "A person rejected the repair or tests failed." : "A person must review the evidence and approve it explicitly.", proposalStatus === "APPROVED" || proposalStatus === "REJECTED"],
    ];
    target.hidden = false; target.className = "repair-card";
    target.innerHTML = `<div class="panel-heading"><div><h3>Repair for ${escapeHTML(shortId(run.id))}</h3><span class="repair-code">${escapeHTML(run.errorCode || "DRIFT")}</span></div><a class="evidence-link" href="/diff.html?run=${encodeURIComponent(run.id)}">Evidence diff</a></div><p><strong>Molt did not guess.</strong> ${escapeHTML(run.errorMessage || "Input drift was detected before output was written.")}</p><div class="repair-grid"><div>Quarantine<strong>${run.quarantine ? "created" : "pending"}</strong></div><div>Active recipe<strong>${escapeHTML(shortId(run.ver))}</strong></div><div>Verification<strong>${escapeHTML(statusText)}</strong></div></div><div class="repair-steps">${steps.map(([title, detail, complete], index) => `<button class="repair-step ${complete ? "complete" : ""}" type="button" aria-expanded="false"><span>${escapeHTML(title)}</span><small>${escapeHTML(detail)}</small></button>`).join("")}</div><div class="repair-warning">Repair proposals are inactive until tests pass and a person approves them.</div><div class="repair-actions"><button class="quiet-button primary" data-mastra-repair="${escapeHTML(run.id)}" ${mastraReady && !proposal ? "" : "disabled"}>Suggest Mastra repair</button>${!mastraReady ? "<small>Mastra sidecar unavailable. Start it at the configured local endpoint.</small>" : ""}${proposal?.status === "PROPOSED" ? `<button class="quiet-button" data-action="verify" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Run repair tests</button>` : ""}${proposal?.status === "PROPOSED" ? "<small>Step 4: run the full regression suite before accepting the repair.</small>" : ""}${proposal?.status === "VERIFIED" ? `<button class="quiet-button" data-action="approve" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Approve repair</button>` : ""}${proposal ? `<button class="quiet-button" data-action="reject" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Reject repair</button>` : ""}</div>`;
  }

  function renderRecipeReview() {
    const target = $("#recipe-review");
    if (!target) return;
    const active = state.versions.find((version) => version.state === "active");
    const candidate = state.versions.find((version) => version.state === "candidate");
    const rejected = state.versions.find((version) => version.state === "rejected");
    const version = candidate || rejected || active;
    if (!version) { target.className = "recipe-review-empty"; target.textContent = "Create an automation and compile a recipe to see its operations, verification result, and human approval state."; $("#recipe-review-status").textContent = "No recipe yet"; return; }
    const recipe = version.recipe || {};
    const checks = version.verification?.checks_total ? `${version.verification.checks_passed || 0}/${version.verification.checks_total} checks passed` : "Verification not run";
    const isActive = version.state === "active";
    const statusLabel = isActive ? "Approved and active" : version.rawStatus === "REJECTED" ? "Not accepted" : version.rawStatus === "AWAITING_APPROVAL" ? "Waiting for human acceptance" : "Candidate awaiting independent verification";
    const statusClass = isActive ? "active" : version.rawStatus === "REJECTED" ? "rejected" : "";
    const repair = repairFor(version.id);
    target.className = "recipe-review";
    target.innerHTML = `<div class="recipe-summary"><div class="recipe-title-row"><span class="recipe-name">${escapeHTML(recipe.name || "Unnamed recipe")}</span><span class="approval-state ${statusClass}">${escapeHTML(statusLabel)}</span></div><p class="recipe-description">${escapeHTML(recipe.description || "No description was stored with this recipe.")}</p><div class="recipe-meta"><div><strong>Version ${escapeHTML(version.v)}</strong><span>${escapeHTML(version.kind)} proposal</span></div><div><strong>${escapeHTML(checks)}</strong><span>independent verification</span></div><div><strong>${escapeHTML(version.provider)}</strong><span>proposal source</span></div></div><div><span class="chart-note">Allowed operations</span><div class="recipe-operations">${recipe.operations?.length ? recipe.operations.map((operation) => `<span class="recipe-operation">${escapeHTML(operation.type || operation.operation || "operation")}</span>`).join("") : "<span class=\"recipe-review-empty\">No operations recorded.</span>"}</div></div></div><div class="recipe-approval"><h3>Human acceptance</h3><p>${isActive ? "A person accepted this recipe after verification. It is the only version allowed on the normal run path." : version.rawStatus === "REJECTED" ? "This candidate was not accepted. It remains recorded for review and cannot run." : "Molt will not activate this draft from model output alone. Review the operations and verification result, then choose an action."}</p><div class="approval-checks">Current state: <strong>${escapeHTML(version.rawStatus)}</strong><br>${escapeHTML(checks)}</div><div class="approval-actions">${version.rawStatus === "DRAFT" || version.rawStatus === "VERIFYING" ? `<button class="quiet-button" data-action="verify" data-id="${escapeHTML(repair ? repair.id : version.id)}" data-kind="${repair ? "repair" : "compile"}">Run tests</button>` : ""}${version.rawStatus === "AWAITING_APPROVAL" && !repair ? `<button class="quiet-button primary" data-action="approve" data-id="${escapeHTML(version.id)}" data-kind="compile">Accept recipe</button>` : ""}${repair?.status === "VERIFIED" ? `<button class="quiet-button primary" data-action="approve" data-id="${escapeHTML(repair.id)}" data-kind="repair">Accept repair</button>` : ""}</div></div>`;
    $("#recipe-review-status").textContent = statusLabel;
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
    const diffLink = `<div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;"><a class="quiet-button primary" href="/diff.html?run=${encodeURIComponent(run.id)}" target="_blank" style="text-decoration:none;display:inline-flex;align-items:center;gap:6px;">Open evidence diff</a>${blocked ? `<button class="quiet-button" data-mastra-repair="${escapeHTML(run.id)}" type="button">Suggest Mastra repair</button>` : ""}</div>`;
    panel.innerHTML = `<div class="inspector-top"><div><h3 class="inspector-title">${blocked ? "Why Molt blocked this file" : "What Molt did with this file"}</h3><p class="inspector-subtitle">${escapeHTML(safeFileName(run.input))} · ${formatDate(run.at)}</p></div><span class="run-status ${blocked ? "blocked" : "success"}">${escapeHTML(run.status.replace(/_/g, " "))}</span></div><div class="inspector-grid"><div class="inspector-stat"><strong>${escapeHTML(run.errorCode || (run.status === "SUCCEEDED" ? "RECIPE_APPLIED" : "RUN_RESULT"))}</strong><span>decision</span></div><div class="inspector-stat"><strong>${run.rows} rows</strong><span>rows written / observed</span></div><div class="inspector-stat"><strong>${run.calls} model calls</strong><span>at execution time</span></div></div><div class="inspector-details">${blocked ? `<p><strong>Molt did not guess.</strong> The input no longer satisfied the approved recipe contract, so no output was written and the file was quarantined for review.</p><p>${escapeHTML(run.errorMessage || "The file was rejected by the deterministic guard.")}</p>${structural}` : `<p><strong>Compatible input.</strong> The stored approved recipe ran deterministically. The model was not called again.</p><p>Output: <code>${escapeHTML(safeFileName(run.output))}</code></p>`}</div>${diffLink}`;
  }

  function renderChart() {
    if (!$("#calls-chart")) return;
    if (!state.runs.length) { $("#calls-chart").innerHTML = `<div class="empty-state">No measured runs yet.</div>`; $("#chart-summary").textContent = "No runs yet"; $("#chart-text-summary").textContent = "No measured runs yet."; return; }
    const runs = state.runs.slice(0, 10).reverse();
    const width = 560; const height = 300; const pad = 34;
    const max = Math.max(1, runs.length);
    const x = (index) => pad + (index * (width - pad * 2)) / Math.max(1, max - 1);
    const y = (calls) => height - pad - Math.min(220, calls * 30);
    const baseline = runs.map((_, index) => `${x(index)},${y(1)}`).join(" ");
    let step = `M${x(0)} ${y(0)}`;
    runs.forEach((_, index) => { if (index) step += ` H${x(index)} V${y(0)}`; });
    const drift = runs.map((run, index) => run.status === "BLOCKED_DRIFT" ? `<line x1="${x(index)}" x2="${x(index)}" y1="${pad}" y2="${height - pad}" stroke="var(--blocked)" stroke-dasharray="4 5"/><text x="${x(index) + 4}" y="${pad + 12}" fill="var(--blocked)" font-size="11">run ${index + 1}</text>` : "").join("");
    $("#calls-chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Model calls compared with deterministic Molt reuse"><defs><pattern id="crosshatch" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M-2 2L2-2M0 10L10 0M8 12L12 8" stroke="#b9bcc2" stroke-width="1" opacity=".5"/><path d="M8-2L12 2M0 0L10 10M-2 8L2 12" stroke="#8d9096" stroke-width=".8" opacity=".42"/></pattern></defs><line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="#4a4d53" stroke-dasharray="1 5" stroke-linecap="round"/><polyline points="${baseline}" fill="none" stroke="var(--ink)" stroke-width="2.2"/><path d="${step}" fill="none" stroke="var(--live)" stroke-width="3.2"/>${drift}<text x="${pad}" y="${height - 10}" fill="var(--muted)" font-size="11">older</text><text x="${width - 74}" y="${height - 10}" fill="var(--muted)" font-size="11">latest</text><text x="${pad}" y="18" fill="var(--muted)" font-size="11">agent prompted every run</text><text x="${width - 150}" y="18" fill="var(--live)" font-size="11">Molt · ${runs.filter((run) => run.status === "SUCCEEDED" && run.calls === 0).length} calls avoided</text></svg>`;
    $("#chart-summary").textContent = `${state.runs.length} measured run${state.runs.length === 1 ? "" : "s"}`;
    $("#chart-text-summary").textContent = `${runs.filter((run) => run.status === "SUCCEEDED" && run.calls === 0).length} successful run(s) reused the recipe without a model call.`;
  }

  function repairFor(versionId) { return state.repairs.find((repair) => String(repair.candidate_version_id) === String(versionId)); }

  function renderVersions() {
    if (!$("#version-summary") || !$("#versions-list")) return;
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
    const body = $("#runs-body");
    if (!body) return;
    body.innerHTML = state.runs.length ? state.runs.map((run) => `<tr class="${run.status === "BLOCKED_DRIFT" ? "blocked" : ""}" data-run-id="${escapeHTML(run.id)}" tabindex="0" title="Select to inspect this run"><td class="result-cell" data-label="Result"><span class="badge ${run.status === "BLOCKED_DRIFT" ? "blocked" : "success"}">${escapeHTML(run.status === "BLOCKED_DRIFT" ? "Blocked: drift" : run.status === "SUCCEEDED" ? "Succeeded" : run.status)}</span><br><span class="run-name">${escapeHTML(shortId(run.id))}</span></td><td data-label="Rows">${run.rows}</td><td data-label="Model calls">${run.calls}</td><td data-label="Recipe">${escapeHTML(shortId(run.ver))}</td><td data-label="Time">${formatMs(run.ms)}</td><td data-label="Evidence"><a class="evidence-link" href="/diff.html?run=${encodeURIComponent(run.id)}">Evidence diff</a></td></tr>`).join("") : `<tr><td class="empty-row" colspan="6">No runs yet. Run a CSV to create evidence.</td></tr>`;
  }

  function render() {
    const selected = state.autos.find((auto) => String(auto.id) === String(state.selected));
    renderTop(selected); renderRail(); renderBuilder(); renderMetric(); renderJourney(selected); renderBeads(); renderRoles(); renderChart(); renderVersions(); renderRuns(); renderRunInspector(); renderRepairCard(); renderRecipeReview();
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

  async function requestMastraRepair(runId) {
    try {
      await post(`/runs/${encodeURIComponent(runId)}/repair`, { model: "mastra" });
      showToast("Mastra repair candidate proposed. Run the regression suite before approval.", "ok");
      await load();
    } catch (error) { showToast(error.message, "error"); }
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
          ? `<strong>Run succeeded.</strong><br>Processed ${record.rows_read} rows in ${record.duration_ms ?? "not measured"} ms with <strong>${record.llm_calls ?? "not measured"} model calls</strong>.<br><small>Output written to: ${escapeHTML(shortId(record.output))}</small>`
          : `<strong>Drift blocked and quarantined.</strong><br>Code: <code>${escapeHTML(record.error_code)}</code> — ${escapeHTML(record.error_message)}<br><small>No output was written. The input was quarantined for review.</small>`;
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
    document.documentElement.dataset.theme = "dark";
    localStorage.setItem("molt-theme", "dark");
    const btn = $("#theme-button");
    if (btn) btn.textContent = "Dark Theme";
  }

  document.addEventListener("click", (event) => {
    const auto = event.target.closest("[data-auto-id]");
    if (auto) { state.selected = auto.dataset.autoId; load(); return; }
    const runRow = event.target.closest("[data-run-id]");
    if (runRow) {
      state.selectedRun = runRow.dataset.runId;
      renderRunInspector();
      renderBeads();
      renderRepairCard();
      $("#run-inspector")?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
      return;
    }
    const lifecycleStep = event.target.closest(".lifecycle-step");
    if (lifecycleStep) { lifecycleStep.setAttribute("aria-expanded", lifecycleStep.getAttribute("aria-expanded") !== "true" ? "true" : "false"); return; }
    const repairStep = event.target.closest(".repair-step");
    if (repairStep) { repairStep.setAttribute("aria-expanded", repairStep.getAttribute("aria-expanded") !== "true" ? "true" : "false"); return; }
    const actionButton = event.target.closest("[data-action]");
    if (actionButton) { action(actionButton); return; }
    const mastraButton = event.target.closest("[data-mastra-repair]");
    if (mastraButton) { requestMastraRepair(mastraButton.dataset.mastraRepair); return; }
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
    if (event.target.closest("#menu-button")) {
      const menu = $("#menu-button"); const rail = $("#workflow-rail"); const expanded = menu.getAttribute("aria-expanded") === "true";
      menu.setAttribute("aria-expanded", String(!expanded)); rail.classList.toggle("open", !expanded);
    }
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

  try {
    const remembered = JSON.parse(localStorage.getItem("molt-temporal-run"));
    if (typeof remembered?.workflow_id === "string") state.temporalRun = remembered;
  } catch (_) { /* An invalid local preference must not prevent dashboard startup. */ }
  localStorage.setItem("molt-theme", "dark");
  setTheme("dark");
  load();
  pollTemporalRun();
}());
