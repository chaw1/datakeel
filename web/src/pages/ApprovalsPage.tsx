import { useState } from "react";

import { ResourceState } from "../components/ResourceState";
import { Button, PageHeader } from "../components/ui";
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
      <PageHeader
        title={t("pageCount", {
          name: t("approvalsNav"),
          count: resource.value?.length ?? 0,
        })}
        actions={
          <Button icon="refresh" iconSize={18} onClick={resource.reload}>
            {t("refresh")}
          </Button>
        }
      />
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
