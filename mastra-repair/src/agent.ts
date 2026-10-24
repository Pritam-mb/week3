import { Agent } from "@mastra/core/agent";
import { repairProposalSchema, type RepairRequest, type RepairProposal } from "./contracts.ts";
import { createRepairTools } from "./tools.ts";

export async function proposeRepair(request: RepairRequest): Promise<{ proposal: RepairProposal; model: string; llm_calls: number }> {
  const model = process.env.MOLT_MASTRA_MODEL;
  if (!model) {
    throw new Error("MOLT_MASTRA_MODEL is required for repair proposals.");
  }
  const agent = new Agent({
    id: "molt-repair-agent",
    name: "Molt Repair Agent",
    instructions: [
      "You propose a repair candidate for a blocked CSV automation.",
      "Use the read-only tools before proposing changes.",
      "Return only the structured repair proposal.",
      "Preserve unrelated active recipe semantics and change only what addresses the structural drift.",
      "Never invent missing source data, raw CSV values, credentials, paths, executable code, or unrestricted operations.",
      "The proposal is not approved. Molt will run its independent regression suite and require explicit human approval.",
    ].join("\n"),
    model,
    tools: createRepairTools(request),
  });
  const result = await agent.generate(
    `Task: ${request.task}
Base recipe version: ${request.base_version_id}
Active Recipe: ${JSON.stringify(request.active_recipe)}
Drift Report: ${JSON.stringify(request.drift_report)}
Masked Profile: ${JSON.stringify(request.profile)}

Instructions:
1. Propose the minimal safe repair for the active recipe addressing the structural drift.
2. In the proposed recipe, you MUST preserve or adapt the operations from the active recipe. The 'operations' array must contain 1-30 operations and never be empty.
3. In input_contract.required_columns and output_contract.required_columns, include only valid non-empty column names. If a column is missing from the input profile, remove it from required columns.
4. Ensure output_contract.preserve_extra_columns is true.`,
    { structuredOutput: { schema: repairProposalSchema } },
  );
  const proposal = repairProposalSchema.parse(result.object);
  return { proposal, model, llm_calls: 1 };
}
