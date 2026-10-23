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
  const params = new URLSearchParams(window.location.hash.split("?")[1]);
  const workflowRun = params.get("workflow_run");
  const selectedPlan = params.get("plan");
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
      {workflowRun && (
        <p>
          <a
            className="button"
            href={`#/workflows?${new URLSearchParams({ run: workflowRun }).toString()}`}
          >
            {t("workflowReturn")}
          </a>
        </p>
      )}
      <ResourceState {...resource} onRetry={resource.reload} />
      {receipts.map((run) => (
        <ActionReceipt key={run.id} run={run} onOpenReceipt={onOpenReceipt} />
      ))}
      {resource.value && (
        <ApprovalList
          plans={
            selectedPlan
              ? resource.value.filter((plan) => plan.id === selectedPlan)
              : resource.value
          }
          onResolved={resolved}
          onOpenReceipt={onOpenReceipt}
        />
      )}
    </>
  );
}
