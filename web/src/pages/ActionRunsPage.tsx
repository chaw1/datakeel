import { useState } from "react";

import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
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
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("operations")}</span>
          <h1>{t("actionHistoryTitle")}</h1>
          <p>{t("actionHistoryDescription")}</p>
        </div>
        <button className="button" onClick={resource.reload}>
          <Icon name="refresh" />
          {t("refresh")}
        </button>
      </div>
      <ResourceState {...resource} onRetry={resource.reload} />
      <div className="section-heading">
        <h2>
          {t("actionHistory")} <span className="count-pill">{runs.length}</span>
        </h2>
        <select
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
        </select>
      </div>
      {!resource.loading && !resource.error && !runs.length && (
        <div className="card empty-state">
          <p>{t(status === "all" ? "noActionRuns" : "noMatchingRuns")}</p>
        </div>
      )}
      <div className="action-run-list">
        {runs.map((run) => (
          <article key={run.id} className="card run-card">
            <ActionReceipt run={run} onOpenReceipt={onOpenReceipt} />
            <details>
              <summary>{t("runDetails")}</summary>
              <pre>{JSON.stringify(run, null, 2)}</pre>
            </details>
          </article>
        ))}
      </div>
    </>
  );
}
