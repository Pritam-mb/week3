import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import type { RepairRequest } from "./contracts.js";

export function createRepairTools(request: RepairRequest) {
  return {
    inspectInputContract: createTool({
      id: "inspect-input-contract",
      description: "Read the masked input profile. This tool never returns CSV cell values or filesystem paths.",
      inputSchema: z.object({}).passthrough(),
      outputSchema: z.record(z.string(), z.unknown()),
      execute: async (_input) => ({
        columns: request.profile.columns ?? [],
        row_count: request.profile.row_count ?? null,
        schema_fingerprint: request.profile.schema_fingerprint ?? null,
      }),
    }),
    inspectDrift: createTool({
      id: "inspect-drift-report",
      description: "Read structural drift evidence for the blocked run.",
      inputSchema: z.object({}).passthrough(),
      outputSchema: z.record(z.string(), z.unknown()),
      execute: async (_input) => request.drift_report,
    }),
    inspectActiveRecipe: createTool({
      id: "inspect-active-recipe",
      description: "Read the approved recipe that the repair must preserve unless the drift requires a change.",
      inputSchema: z.object({}).passthrough(),
      outputSchema: z.record(z.string(), z.unknown()),
      execute: async (_input) => request.active_recipe,
    }),
  };
}
