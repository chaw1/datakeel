import type { ActionPlan } from "../../api/types";

export function requiresHumanApproval(plan: ActionPlan) {
  return (
    !plan.reversible ||
    plan.external ||
    [
      "update_standard",
      "update_code_list",
      "import_standards",
      "confirm_standard_mapping",
      "rollback_standards",
    ].includes(plan.action_type)
  );
}
