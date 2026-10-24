import { z } from "zod";

export const recipeSchema = z.object({
  schema_version: z.literal(1),
  name: z.string(),
  description: z.string(),
  input_contract: z.object({
    required_columns: z.array(z.string()),
  }).passthrough(),
  operations: z.array(z.record(z.string(), z.unknown())).min(1).max(30),
  output_contract: z.object({
    required_columns: z.array(z.string()),
    preserve_extra_columns: z.literal(true),
  }).passthrough(),
}).passthrough();

export const repairRequestSchema = z.object({
  automation_id: z.string().min(1),
  run_id: z.string().nullable().optional(),
  task: z.string().min(1),
  base_version_id: z.string().min(1),
  active_recipe: recipeSchema,
  drift_report: z.record(z.string(), z.unknown()),
  profile: z.record(z.string(), z.unknown()),
});

export const repairProposalSchema = z.object({
  reason: z.string().min(1),
  changes: z.array(z.object({
    operation: z.string(),
    rationale: z.string(),
  })).max(30),
  assumptions: z.array(z.string()).max(20),
  recipe: recipeSchema,
});

export type RepairRequest = z.infer<typeof repairRequestSchema>;
export type RepairProposal = z.infer<typeof repairProposalSchema>;
