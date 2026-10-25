with open('molt/web/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

old_action_buttons = """    const actionButtons = proposalStatus === "APPROVED"
      ? `<div style="display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:var(--live);padding:8px 12px;background:rgba(16,185,129,0.1);border-radius:6px;border:1px solid rgba(16,185,129,0.25);">✓ Repair was approved and activated. New runs (such as run 5) now process cleanly with the repaired recipe.</div>`
      : `<button class="quiet-button primary" data-mastra-repair="${escapeHTML(run.id)}" ${mastraReady && !proposal ? "" : "disabled"}>Suggest Mastra repair</button>${!mastraReady ? "<small>Mastra sidecar unavailable. Start it at the configured local endpoint.</small>" : ""}${proposal?.status === "PROPOSED" ? `<button class="quiet-button" data-action="verify" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Run repair tests</button>` : ""}${proposal?.status === "PROPOSED" ? "<small>Step 4: run the full regression suite before accepting the repair.</small>" : ""}${proposal?.status === "VERIFIED" ? `<button class="quiet-button" data-action="approve" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Approve repair</button>` : ""}${proposal ? `<button class="quiet-button" data-action="reject" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Reject repair</button>` : ""}`;"""

new_action_buttons = """    const actionButtons = proposalStatus === "APPROVED"
      ? `<div style="display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:var(--live);padding:8px 12px;background:rgba(16,185,129,0.1);border-radius:6px;border:1px solid rgba(16,185,129,0.25);">✓ Repair was approved and activated. New runs now process cleanly with the repaired recipe.</div>`
      : proposalStatus === "REJECTED"
      ? `<div style="display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--blocked);padding:10px 14px;background:rgba(255,90,60,0.08);border-radius:6px;border:1px solid rgba(255,90,60,0.3);width:100%;"><strong>⚠ Candidate rejected by regression verification</strong><span>Molt tested Mastra's repair proposal against golden regression fixtures. The candidate failed independent verification (e.g. dropped required columns), so Molt safely refused to activate it. Production data was protected.</span></div><button class="quiet-button" data-mastra-repair="${escapeHTML(run.id)}" ${mastraReady ? "" : "disabled"} style="margin-top:8px;">Suggest Mastra repair again</button>`
      : `<button class="quiet-button primary" data-mastra-repair="${escapeHTML(run.id)}" ${mastraReady && !proposal ? "" : "disabled"}>Suggest Mastra repair</button>${!mastraReady ? "<small>Mastra sidecar unavailable. Start it at the configured local endpoint.</small>" : ""}${proposal?.status === "PROPOSED" ? `<button class="quiet-button" data-action="verify" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Run repair tests</button>` : ""}${proposal?.status === "PROPOSED" ? "<small>Step 4: run the full regression suite before accepting the repair.</small>" : ""}${proposal?.status === "VERIFIED" ? `<button class="quiet-button" data-action="approve" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Approve repair</button>` : ""}${proposal ? `<button class="quiet-button" data-action="reject" data-id="${escapeHTML(proposal.id)}" data-kind="repair">Reject repair</button>` : ""}`;"""

assert old_action_buttons in content, "old_action_buttons not found"
content = content.replace(old_action_buttons, new_action_buttons, 1)

with open('molt/web/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated renderRepairCard in app.js successfully!")
