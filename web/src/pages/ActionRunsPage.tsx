import { useState } from "react";

import { ResourceState } from "../components/ResourceState";
import {
  Button,
  EmptyState,
  PageHeader,
  Select,
  Surface,
} from "../components/ui";
import { ActionReceipt } from "../features/actions/ActionReceipt";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { ActionRun } from "../api/types";
import type { LineageTarget } from "../app/navigation";

export function ActionRunsPage({
  onOpenReceipt,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const resource = useResource<ActionRun[]>("/api/actions/runs");
  const [status, setStatus] = useState("all");
  const states = [
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "DENIED",
  ] as const;
  const runs =
    resource.value?.filter(
      (run) => status === "all" || run.status === status,
    ) ?? [];
  return (
    <>
      <PageHeader
        eyebrow={t("operations")}
        title={t("actionHistoryTitle")}
        subtitle={t("actionHistoryDescription")}
        actions={
          <Button icon="refresh" onClick={resource.reload}>
            {t("refresh")}
          </Button>
        }
      />
      <ResourceState {...resource} onRetry={resource.reload} />
      <div className="section-heading">
        <h2>
          {t("actionHistory")} <span className="count-pill">{runs.length}</span>
        </h2>
        <Select
          aria-label={t("filterRunStatus")}
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
          }}
          onBlur={(event) => {
            setStatus(event.target.value);
          }}
        >
          <option value="all">{t("allStates")}</option>
          {states.map((state) => (
            <option key={state} value={state}>
              {t(state)}
            </option>
          ))}
        </Select>
      </div>
      {!resource.loading && !resource.error && !runs.length && (
        <EmptyState
          card
          title={t(status === "all" ? "noActionRuns" : "noMatchingRuns")}
        />
      )}
      <div className="action-run-list">
        {runs.map((run) => (
          <Surface as="article" key={run.id} className="run-card">
            <ActionReceipt run={run} onOpenReceipt={onOpenReceipt} />
            <details>
              <summary>{t("runDetails")}</summary>
              <pre>{JSON.stringify(run, null, 2)}</pre>
            </details>
          </Surface>
        ))}
      </div>
    </>
  );
}
