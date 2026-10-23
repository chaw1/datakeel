import { useState } from "react";

import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import { ActionReceipt } from "../features/actions/ActionReceipt";
import { ApprovalList } from "../features/approvals/ApprovalList";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { ActionPlan, ActionRun } from "../api/types";
import type { LineageTarget } from "../app/navigation";

export function ApprovalsPage({
  onOpenReceipt,
  onDataChanged,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
  onDataChanged: () => void;
}) {
  const { t } = useI18n();
  const resource = useResource<ActionPlan[]>("/api/approvals");
  const [receipts, setReceipts] = useState<ActionRun[]>([]);
  function resolved(run: ActionRun | null) {
    if (run) setReceipts((current) => [run, ...current]);
    resource.reload();
    onDataChanged();
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>
            {t("pageCount", {
              name: t("approvalsNav"),
              count: resource.value?.length ?? 0,
            })}
          </h1>
        </div>
        <button className="button" onClick={resource.reload}>
          <Icon name="refresh" />
          {t("refresh")}
        </button>
      </div>
      <ResourceState {...resource} onRetry={resource.reload} />
      {receipts.map((run) => (
        <ActionReceipt key={run.id} run={run} onOpenReceipt={onOpenReceipt} />
      ))}
      {resource.value && (
        <ApprovalList
          plans={resource.value}
          onResolved={resolved}
          onOpenReceipt={onOpenReceipt}
        />
      )}
    </>
  );
}
