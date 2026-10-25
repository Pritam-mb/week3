with open('molt/web/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update fromApi
old_from_api = """    state.versions = list(detail.versions).map(mapVersion);
    state.repairs = list(detail.repair_proposals);
    state.builder.sourcePath = state.builder.sourcePath || selected?.inputReference || "";
    return { selected, detail };"""

new_from_api = """    state.versions = list(detail.versions).map(mapVersion);
    state.repairs = list(detail.repair_proposals);
    state.builder.sourcePath = state.builder.sourcePath || selected?.inputReference || "";
    if (!state.selectedRun || !state.runs.some((r) => String(r.id) === String(state.selectedRun))) {
      state.selectedRun = state.runs[0]?.id || null;
    }
    return { selected, detail };"""

assert old_from_api in content, 'old_from_api not found'
content = content.replace(old_from_api, new_from_api, 1)

# 2. Update renderBeads
old_render_beads = """  function renderBeads() {
    const target = $("#run-beads");
    if (!target) return;
    if (!state.runs.length) { target.innerHTML = `<span class="empty-state">No runs yet.</span>`; $("#result-sentence").textContent = "No runs yet. Run a compatible CSV to create evidence."; return; }
    const activeVersion = state.versions.find((version) => version.state === "active");
    target.innerHTML = `${activeVersion ? `<div class="version-divider">v${escapeHTML(activeVersion.v)} active</div>` : ""}${state.runs.map((run, index) => `<button class="run-bead ${run.status === "BLOCKED_DRIFT" ? "blocked" : ""}" type="button" data-run-id="${escapeHTML(run.id)}" aria-label="${escapeHTML(run.status)} run ${index + 1}"><i></i><span>run ${index + 1}</span></button>`).join("")}`;
    const latest = state.runs[0];
    $("#result-sentence").textContent = latest.status === "BLOCKED_DRIFT" ? "Latest result: input drift was detected before output was written." : "Latest result: compatible input reused the approved recipe with no model call during execution.";
  }"""

new_render_beads = """  function renderBeads() {
    const target = $("#run-beads");
    if (!target) return;
    if (!state.runs.length) { target.innerHTML = `<span class="empty-state">No runs yet.</span>`; $("#result-sentence").textContent = "No runs yet. Run a compatible CSV to create evidence."; return; }
    const activeVersion = state.versions.find((version) => version.state === "active");
    const chronological = state.runs.slice().reverse();
    target.innerHTML = `${activeVersion ? `<div class="version-divider">v${escapeHTML(activeVersion.v)} active</div>` : ""}${chronological.map((run, index) => {
      const isLatest = index === chronological.length - 1;
      const isSelected = String(run.id) === String(state.selectedRun);
      const runNum = index + 1;
      return `<button class="run-bead ${run.status === "BLOCKED_DRIFT" ? "blocked" : ""} ${isSelected ? "selected" : ""}" type="button" data-run-id="${escapeHTML(run.id)}" aria-label="${escapeHTML(run.status)} run ${runNum}"><i></i><span>run ${runNum}${isLatest ? " (latest)" : ""}</span></button>`;
    }).join("")}`;
    const latest = state.runs[0];
    $("#result-sentence").textContent = latest.status === "BLOCKED_DRIFT" ? "Latest result: input drift was detected before output was written." : "Latest result: compatible input reused the approved recipe with no model call during execution.";
  }"""

assert old_render_beads in content, 'old_render_beads not found'
content = content.replace(old_render_beads, new_render_beads, 1)

# 3. Update renderRuns
old_render_runs = """  function renderRuns() {
    const body = $("#runs-body");
    if (!body) return;
    body.innerHTML = state.runs.length ? state.runs.map((run) => `<tr class="${run.status === "BLOCKED_DRIFT" ? "blocked" : ""}" data-run-id="${escapeHTML(run.id)}" tabindex="0" title="Select to inspect this run"><td class="result-cell" data-label="Result"><span class="badge ${run.status === "BLOCKED_DRIFT" ? "blocked" : "success"}">${escapeHTML(run.status === "BLOCKED_DRIFT" ? "Blocked: drift" : run.status === "SUCCEEDED" ? "Succeeded" : run.status)}</span><br><span class="run-name">${escapeHTML(shortId(run.id))}</span></td><td data-label="Rows">${run.rows}</td><td data-label="Model calls">${run.calls}</td><td data-label="Recipe">${escapeHTML(shortId(run.ver))}</td><td data-label="Time">${formatMs(run.ms)}</td><td data-label="Evidence"><a class="evidence-link" href="/diff.html?run=${encodeURIComponent(run.id)}">Evidence diff</a></td></tr>`).join("") : `<tr><td class="empty-row" colspan="6">No runs yet. Run a CSV to create evidence.</td></tr>`;
  }"""

new_render_runs = """  function renderRuns() {
    const body = $("#runs-body");
    if (!body) return;
    const total = state.runs.length;
    body.innerHTML = state.runs.length ? state.runs.map((run, index) => {
      const runNum = total - index;
      const isLatest = index === 0;
      const isSelected = String(run.id) === String(state.selectedRun);
      return `<tr class="${run.status === "BLOCKED_DRIFT" ? "blocked" : ""} ${isSelected ? "selected" : ""}" data-run-id="${escapeHTML(run.id)}" tabindex="0" title="Select to inspect this run"><td class="result-cell" data-label="Result"><span class="badge ${run.status === "BLOCKED_DRIFT" ? "blocked" : "success"}">${escapeHTML(run.status === "BLOCKED_DRIFT" ? "Blocked: drift" : run.status === "SUCCEEDED" ? "Succeeded" : run.status)}</span><br><span class="run-name">Run ${runNum}${isLatest ? " (latest)" : ""} · ${escapeHTML(shortId(run.id))}</span></td><td data-label="Rows">${run.rows}</td><td data-label="Model calls">${run.calls}</td><td data-label="Recipe">${escapeHTML(shortId(run.ver))}</td><td data-label="Time">${formatMs(run.ms)}</td><td data-label="Evidence"><a class="evidence-link" href="/diff.html?run=${encodeURIComponent(run.id)}">Evidence diff</a></td></tr>`;
    }).join("") : `<tr><td class="empty-row" colspan="6">No runs yet. Run a CSV to create evidence.</td></tr>`;
  }"""

assert old_render_runs in content, 'old_render_runs not found'
content = content.replace(old_render_runs, new_render_runs, 1)

# 4. Update auto switch click
old_auto_click = 'const auto = event.target.closest("[data-auto-id]");\n    if (auto) { state.selected = auto.dataset.autoId; load(); return; }'
new_auto_click = 'const auto = event.target.closest("[data-auto-id]");\n    if (auto) { state.selected = auto.dataset.autoId; state.selectedRun = null; load(); return; }'
assert old_auto_click in content, 'old_auto_click not found'
content = content.replace(old_auto_click, new_auto_click, 1)

with open('molt/web/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('app.js successfully updated!')
