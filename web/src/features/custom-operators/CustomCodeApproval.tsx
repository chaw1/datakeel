import { SourceReview } from "./SourceReview";

import type { StaticCheck } from "../../api/customOperators";
import type { ActionPlan } from "../../api/types";

function isCheck(value: unknown): value is StaticCheck {
  return (
    typeof value === "object" &&
    value !== null &&
    "line" in value &&
    typeof value.line === "number" &&
    "column" in value &&
    typeof value.column === "number" &&
    "code" in value &&
    typeof value.code === "string" &&
    "message" in value &&
    typeof value.message === "string"
  );
}

export function CustomCodeApproval({ plan }: { plan: ActionPlan }) {
  if (plan.action_type !== "submit_custom_operator") return null;
  const params = plan.canonical_params;
  const checks = Array.isArray(params.static_checks)
    ? params.static_checks.filter(isCheck)
    : [];
  return (
    <SourceReview
      code={typeof params.code === "string" ? params.code : ""}
      codeHash={typeof params.code_hash === "string" ? params.code_hash : ""}
      checks={checks}
    />
  );
}
