import type { ActionPlan } from "../../../api/types";

/** One rework round a prepared assignment plan moves from its original annotator to someone else. */
export interface ReworkHandover {
  task_id: string;
  round: number;
  from_actor: string;
  to_actor: string;
}

function isHandover(value: unknown): value is ReworkHandover {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.task_id === "string" &&
    typeof item.round === "number" &&
    typeof item.from_actor === "string" &&
    typeof item.to_actor === "string"
  );
}

/** Read the handovers the server wrote into a prepared `assign_tasks` plan. */
export function planHandovers(plan: ActionPlan): ReworkHandover[] {
  const value: unknown = plan.canonical_params.transfers;
  return Array.isArray(value) ? value.filter(isHandover) : [];
}
