import { ApprovalSheet } from "../approvals/ApprovalSheet";

import type { ApprovalProps } from "../approvals/useApproval";

export function PlanCard(props: ApprovalProps) {
  return (
    <ApprovalSheet
      key={`${props.plan.id}:${props.plan.plan_digest}`}
      {...props}
    />
  );
}
