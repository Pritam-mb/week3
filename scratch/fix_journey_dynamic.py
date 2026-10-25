with open('molt/web/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

old_journey_block = """  function renderJourney(selected) {
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
    ];"""

new_journey_block = """  function renderJourney(selected) {
    const activeVersion = state.versions.find((version) => version.state === "active");
    const active = Boolean(activeVersion);
    const activeNum = activeVersion ? `v${activeVersion.v}` : "active";
    const candidate = state.versions.some((version) => version.state === "candidate");
    const rejected = state.versions.some((version) => version.state === "rejected");
    const blocked = state.runs.some((run) => run.status === "BLOCKED_DRIFT");
    const latest = state.runs[0];
    const latestSucceeded = latest?.status === "SUCCEEDED";
    const latestRepair = state.repairs[state.repairs.length - 1];
    const repairPending = state.repairs.some((repair) => ["PROPOSED", "VERIFIED"].includes(repair.status));
    const repairRejected = latestRepair?.status === "REJECTED";
    const repairApproved = state.repairs.some((repair) => repair.status === "APPROVED");

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
          ? `Active recipe ${activeNum} passed its full regression suite.`
          : "No candidate has been created yet.",
        statusText: candidate ? "Review" : repairRejected ? "Candidate rejected (4/8)" : active ? "Passed" : "Waiting",
        tone: candidate ? "warn" : repairRejected ? "blocked" : active ? "done" : "",
        next: "A failed candidate stays inactive."
      },
      {
        title: "Human approval",
        detail: active
          ? `A person approved verified recipe ${activeNum}. It is the active version for execution.`
          : candidate
          ? "A person reviews the recipe and explicitly approves it after tests pass."
          : "Only an approved recipe can run.",
        statusText: candidate ? "Action needed" : repairRejected ? "Candidate not accepted" : active ? `Approved (${activeNum})` : "Waiting",
        tone: candidate ? "warn" : repairRejected ? "blocked" : active ? "done" : "",
        next: "Only an approved recipe can run."
      },
      {
        title: "Run deterministically",
        detail: latest
          ? `${latest.calls} model calls were recorded. Stored active recipe ${activeNum} executed deterministically.`
          : "The approved recipe is reused without another model call.",
        statusText: latest ? (latestSucceeded ? `Reused ${activeNum} (0 calls)` : "Blocked by drift") : "Waiting",
        tone: latest ? (latestSucceeded ? "done" : "blocked") : "",
        next: "Compatible input produces an atomic output."
      },
      {
        title: "Drift blocked",
        detail: blocked
          ? (latestSucceeded ? "Past runs were quarantined due to drift; the approved repair resolved it." : "Input drift was detected in past runs. The input was quarantined without writing unverified output.")
          : "This step appears only when a file changes in an unapproved way.",
        statusText: blocked ? (latestSucceeded ? "Drift resolved" : "Blocked") : "Not triggered",
        tone: blocked ? (latestSucceeded ? "done" : "blocked") : "",
        next: "Select a blocked run to review drift evidence."
      },
      {
        title: "Mastra repair proposal",
        detail: repairRejected
          ? `Mastra proposal was tested and REJECTED by Molt. Active ${activeNum} remains in effect.`
          : repairApproved && latestSucceeded
          ? `Mastra repair was approved and activated as ${activeNum}. New runs execute cleanly.`
          : repairPending
          ? "Mastra returned a candidate, but it is not active until tested and approved."
          : blocked
          ? "Drift occurred. You can ask Mastra to propose a recipe repair."
          : "Normal pipeline active.",
        statusText: repairRejected ? "Proposal rejected" : (repairApproved && latestSucceeded) ? "Repair active" : repairPending ? "Candidate stored" : blocked ? "Ready" : "Waiting",
        tone: repairRejected ? "blocked" : (repairApproved && latestSucceeded) ? "done" : repairPending ? "warn" : "",
        next: "Next: run the full regression suite."
      }
    ];"""

assert old_journey_block in content, "old_journey_block not found"
content = content.replace(old_journey_block, new_journey_block, 1)

with open('molt/web/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated renderJourney in app.js successfully!")
