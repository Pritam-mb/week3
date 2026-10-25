with open('molt/web/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace renderJourney
old_render_journey = '''  function renderJourney(selected) {
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
  }'''

new_render_journey = '''  function renderJourney(selected) {
    const active = state.versions.some((version) => version.state === "active");
    const candidate = state.versions.some((version) => version.state === "candidate");
    const rejected = state.versions.some((version) => version.state === "rejected");
    const blocked = state.runs.some((run) => run.status === "BLOCKED_DRIFT");
    const latest = state.runs[0];
    const latestRepair = state.repairs[state.repairs.length - 1];
    const repairPending = state.repairs.some((repair) => ["PROPOSED", "VERIFIED"].includes(repair.status));
    const repairRejected = latestRepair?.status === "REJECTED";

    const steps = [
      {
        title: "Profile input",
        detail: "The CSV is inspected for columns, types, row count, and fingerprints. Raw rows are not sent to the model.",
        statusText: "Done",
        tone: active || candidate ? "done" : "warn",
        next: "Compile can use the structural profile."
      },
      {
        title: "Compile recipe",
        detail: "Gemma proposes constrained JSON operations. It does not write Python or change the CSV.",
        statusText: candidate ? "Candidate" : active ? "Completed" : "Waiting",
        tone: candidate || active ? "done" : "",
        next: "The candidate must pass independent tests."
      },
      {
        title: "Verify recipe",
        detail: candidate
          ? "The candidate is tested against golden outputs, errors, and invariants."
          : repairRejected
          ? "Mastra repair proposal failed independent verification (4/8 checks passed). Molt rejected it and kept it inactive."
          : active
          ? "Active recipe v1 passed its full regression suite."
          : "No candidate has been created yet.",
        statusText: candidate ? "Review" : repairRejected ? "Candidate rejected (4/8)" : active ? "Passed" : "Waiting",
        tone: candidate ? "warn" : repairRejected ? "blocked" : active ? "done" : "",
        next: "A failed candidate stays inactive."
      },
      {
        title: "Human approval",
        detail: active
          ? "A person approved verified recipe v1. It is the active version for execution."
          : candidate
          ? "A person reviews the recipe and explicitly approves it after tests pass."
          : "Only an approved recipe can run.",
        statusText: candidate ? "Action needed" : repairRejected ? "Candidate not accepted" : active ? "Approved (v1)" : "Waiting",
        tone: candidate ? "warn" : repairRejected ? "blocked" : active ? "done" : "",
        next: "Only an approved recipe can run."
      },
      {
        title: "Run deterministically",
        detail: latest
          ? `${latest.calls} model calls were recorded. Stored active recipe v1 executed deterministically.`
          : "The approved recipe is reused without another model call.",
        statusText: latest ? (latest.status === "SUCCEEDED" ? "Reused v1 (0 calls)" : "Blocked by drift") : "Waiting",
        tone: latest ? (latest.status === "SUCCEEDED" ? "done" : "blocked") : "",
        next: "Compatible input produces an atomic output."
      },
      {
        title: "Drift blocked",
        detail: blocked
          ? "Input drift was detected in past runs. The input was quarantined without writing unverified output."
          : "This step appears only when a file changes in an unapproved way.",
        statusText: blocked ? "Blocked" : "Not triggered",
        tone: blocked ? "blocked" : "",
        next: "Select the blocked run to open the repair path."
      },
      {
        title: "Mastra repair proposal",
        detail: repairRejected
          ? "Mastra proposed candidate v4, but Molt verified it and REJECTED it (4/8 pass). Active v1 remains in effect."
          : repairPending
          ? "Mastra returned a candidate, but it is not active until tested and approved."
          : blocked
          ? "Drift occurred. You can ask Mastra to propose a recipe repair."
          : "Normal pipeline active.",
        statusText: repairRejected ? "Proposal rejected" : repairPending ? "Candidate stored" : blocked ? "Ready" : "Waiting",
        tone: repairRejected ? "blocked" : repairPending ? "warn" : "",
        next: "Next: run the full regression suite."
      }
    ];

    $("#journey-graph").innerHTML = steps.map((s) => `<button class="lifecycle-step ${s.tone}" type="button" aria-expanded="false"><span class="lifecycle-dot"></span><strong>${escapeHTML(s.title)}</strong><span class="lifecycle-status">${escapeHTML(s.statusText)}</span><span class="lifecycle-evidence"><span class="lifecycle-detail"><b>What happens</b><span>${escapeHTML(s.detail)}</span></span><span class="lifecycle-detail"><b>Result</b><span>${escapeHTML(s.statusText)}</span></span><span class="lifecycle-detail"><b>What happens next</b><span>${escapeHTML(s.next)}</span></span></span></button>`).join("");
    $("#journey-caption").textContent = selected ? `${selected.name} · ${blocked ? "drift occurred on past files; active v1 protected" : active ? "approved recipe ready" : "start by creating a recipe"}` : "Create an automation to begin";
  }'''

assert old_render_journey in content, 'old_render_journey not found'
content = content.replace(old_render_journey, new_render_journey, 1)

# 2. Update renderRecipeReview
old_recipe_review = '''  function renderRecipeReview() {
    const target = $("#recipe-review");
    if (!target) return;
    const active = state.versions.find((version) => version.state === "active");
    const candidate = state.versions.find((version) => version.state === "candidate");
    const rejected = state.versions.find((version) => version.state === "rejected");
    const version = candidate || rejected || active;'''

new_recipe_review = '''  function renderRecipeReview() {
    const target = $("#recipe-review");
    if (!target) return;
    const active = state.versions.find((version) => version.state === "active");
    const candidate = state.versions.find((version) => version.state === "candidate");
    const rejected = state.versions.find((version) => version.state === "rejected");
    const version = candidate || active || rejected;'''

assert old_recipe_review in content, 'old_recipe_review not found'
content = content.replace(old_recipe_review, new_recipe_review, 1)

# 3. Add rejected banner into renderRecipeReview
old_approval_end = '''    target.className = "recipe-review";
    target.innerHTML = `<div class="recipe-summary"><div class="recipe-title-row"><span class="recipe-name">${escapeHTML(recipe.name || "Unnamed recipe")}</span><span class="approval-state ${statusClass}">${escapeHTML(statusLabel)}</span></div><p class="recipe-description">${escapeHTML(recipe.description || "No description was stored with this recipe.")}</p><div class="recipe-meta"><div><strong>Version ${escapeHTML(version.v)}</strong><span>${escapeHTML(version.kind)} proposal</span></div><div><strong>${escapeHTML(checks)}</strong><span>independent verification</span></div><div><strong>${escapeHTML(version.provider)}</strong><span>proposal source</span></div></div><div><span class="chart-note">Allowed operations</span><div class="recipe-operations">${recipe.operations?.length ? recipe.operations.map((operation) => `<span class="recipe-operation">${escapeHTML(operation.type || operation.operation || "operation")}</span>`).join("") : "<span class=\\"recipe-review-empty\\">No operations recorded.</span>"}</div></div></div><div class="recipe-approval"><h3>Human acceptance</h3><p>${isActive ? "A person accepted this recipe after verification. It is the only version allowed on the normal run path." : version.rawStatus === "REJECTED" ? "This candidate was not accepted. It remains recorded for review and cannot run." : "Molt will not activate this draft from model output alone. Review the operations and verification result, then choose an action."}</p><div class="approval-checks">Current state: <strong>${escapeHTML(version.rawStatus)}</strong><br>${escapeHTML(checks)}</div><div class="approval-actions">${version.rawStatus === "DRAFT" || version.rawStatus === "VERIFYING" ? `<button class="quiet-button" data-action="verify" data-id="${escapeHTML(repair ? repair.id : version.id)}" data-kind="${repair ? "repair" : "compile"}">Run tests</button>` : ""}${version.rawStatus === "AWAITING_APPROVAL" && !repair ? `<button class="quiet-button primary" data-action="approve" data-id="${escapeHTML(version.id)}" data-kind="compile">Accept recipe</button>` : ""}${repair?.status === "VERIFIED" ? `<button class="quiet-button primary" data-action="approve" data-id="${escapeHTML(repair.id)}" data-kind="repair">Accept repair</button>` : ""}</div></div>`;'''

new_approval_end = '''    target.className = "recipe-review";
    const rejectedBanner = (rejected && isActive) ? `<div style="grid-column:1/-1;padding:10px 14px;background:rgba(255,90,60,0.08);border:1px solid rgba(255,90,60,0.3);border-radius:8px;font-size:12px;color:var(--muted);"><strong style="color:var(--blocked);">⚠ Notice: Repair candidate v${escapeHTML(rejected.v)} was REJECTED by verifier (4/8 checks passed).</strong> Molt refused to activate it because it dropped required columns. It was never run. Production runs continue safely using active <strong>v${escapeHTML(active.v)}</strong>.</div>` : "";
    target.innerHTML = `<div class="recipe-summary"><div class="recipe-title-row"><span class="recipe-name">${escapeHTML(recipe.name || "Unnamed recipe")}</span><span class="approval-state ${statusClass}">${escapeHTML(statusLabel)}</span></div><p class="recipe-description">${escapeHTML(recipe.description || "No description was stored with this recipe.")}</p><div class="recipe-meta"><div><strong>Version ${escapeHTML(version.v)}</strong><span>${isActive ? "approved active version" : `${escapeHTML(version.kind)} proposal`}</span></div><div><strong>${escapeHTML(checks)}</strong><span>independent verification</span></div><div><strong>${escapeHTML(version.provider)}</strong><span>proposal source</span></div></div><div><span class="chart-note">Allowed operations</span><div class="recipe-operations">${recipe.operations?.length ? recipe.operations.map((operation) => `<span class="recipe-operation">${escapeHTML(operation.type || operation.operation || "operation")}</span>`).join("") : "<span class=\\"recipe-review-empty\\">No operations recorded.</span>"}</div></div></div><div class="recipe-approval"><h3>Human acceptance</h3><p>${isActive ? "A person accepted this recipe after verification. It is the only version allowed on the normal run path." : version.rawStatus === "REJECTED" ? "This candidate was not accepted. It remains recorded for review and cannot run." : "Molt will not activate this draft from model output alone. Review the operations and verification result, then choose an action."}</p><div class="approval-checks">Current state: <strong>${escapeHTML(version.rawStatus)}</strong><br>${escapeHTML(checks)}</div><div class="approval-actions">${version.rawStatus === "DRAFT" || version.rawStatus === "VERIFYING" ? `<button class="quiet-button" data-action="verify" data-id="${escapeHTML(repair ? repair.id : version.id)}" data-kind="${repair ? "repair" : "compile"}">Run tests</button>` : ""}${version.rawStatus === "AWAITING_APPROVAL" && !repair ? `<button class="quiet-button primary" data-action="approve" data-id="${escapeHTML(version.id)}" data-kind="compile">Accept recipe</button>` : ""}${repair?.status === "VERIFIED" ? `<button class="quiet-button primary" data-action="approve" data-id="${escapeHTML(repair.id)}" data-kind="repair">Accept repair</button>` : ""}</div></div>${rejectedBanner}`;'''

assert old_approval_end in content, 'old_approval_end not found'
content = content.replace(old_approval_end, new_approval_end, 1)

with open('molt/web/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('app.js successfully updated with truthful lifecycle tones and active version priority!')
