import { useState } from "react";

import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import {
  workflowDescription,
  workflowName,
} from "../features/workflows/labels";
import { useWorkflowRun } from "../features/workflows/useWorkflowRun";
import { WorkflowForm } from "../features/workflows/WorkflowForm";
import { WorkflowHistory } from "../features/workflows/WorkflowHistory";
import { WorkflowTimeline } from "../features/workflows/WorkflowTimeline";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { Dataset } from "../api/types";
import type { WorkflowDefinition, WorkflowRun } from "../api/workflows";

import "../features/workflows/workflows.css";

export function WorkflowsPage({
  datasets,
  onDataChanged,
}: {
  datasets: Dataset[];
  onDataChanged: () => void;
}) {
  const { t } = useI18n();
  const params = new URLSearchParams(window.location.hash.split("?")[1]);
  const definitions = useResource<WorkflowDefinition[]>("/api/workflows");
  const history = useResource<WorkflowRun[]>("/api/workflows/runs");
  const [selectedId, setSelectedId] = useState(params.get("workflow") ?? "");
  const id = selectedId || definitions.value?.[0]?.id || "";
  const definition = useResource<WorkflowDefinition>(
    id ? `/api/workflows/${encodeURIComponent(id)}` : null,
  );
  const session = useWorkflowRun(params.get("run") ?? "", () => {
    history.reload();
    onDataChanged();
  });
  const [showForm, setShowForm] = useState(!params.has("run"));
  function refresh() {
    definitions.reload();
    definition.reload();
    history.reload();
    session.reload();
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{t("workflowsNav")}</h1>
          <p className="muted">{t("workflowIntro")}</p>
        </div>
        <button className="button" disabled={session.busy} onClick={refresh}>
          <Icon name="refresh" />
          {t("refresh")}
        </button>
      </div>
      <ResourceState
        loading={definitions.loading}
        error={definitions.error || history.error}
        onRetry={refresh}
      />
      <div className="workflows-layout">
        <section
          className="workflow-list"
          aria-label={t("workflowDefinitions")}
        >
          <h2>{t("workflowDefinitions")}</h2>
          {definitions.value?.map((item) => (
            <button
              key={item.id}
              className={`card workflow-card ${showForm && id === item.id ? "selected" : ""}`}
              disabled={session.busy}
              onClick={() => {
                setSelectedId(item.id);
                setShowForm(true);
                window.history.replaceState(
                  null,
                  "",
                  `/#/workflows?${new URLSearchParams({ workflow: item.id }).toString()}`,
                );
              }}
            >
              <Icon name="activity" />
              <strong>{workflowName(item.id, t, item.name)}</strong>
              <span>{workflowDescription(item.id, t, item.description)}</span>
              <code>{item.id}</code>
            </button>
          ))}
          {definitions.value?.length === 0 && (
            <p className="muted">{t("workflowNoDefinitions")}</p>
          )}
        </section>
        <div className="workflow-main">
          {session.error && (
            <div className="error-banner" role="alert">
              <div>
                {session.interrupted && (
                  <strong>{t("workflowStreamError")}</strong>
                )}
                <p>{session.error}</p>
                <button disabled={session.busy} onClick={session.reload}>
                  {t("workflowReload")}
                </button>
              </div>
            </div>
          )}
          {showForm ? (
            <>
              <ResourceState {...definition} onRetry={definition.reload} />
              {definition.value && (
                <WorkflowForm
                  key={definition.value.id}
                  definition={definition.value}
                  datasets={datasets}
                  datasetId={params.get("dataset") ?? ""}
                  busy={session.busy}
                  onStart={(inputs) => {
                    setShowForm(false);
                    void session.start(id, inputs);
                  }}
                />
              )}
            </>
          ) : (
            <>
              <ResourceState
                loading={session.loading}
                error=""
                onRetry={session.reload}
              />
              {session.busy && <p role="status">{t("workflowRunning")}</p>}
              {session.value && (
                <WorkflowTimeline
                  run={session.value}
                  busy={session.busy}
                  onResume={() => {
                    void session.resume();
                  }}
                />
              )}
            </>
          )}
        </div>
      </div>
      <WorkflowHistory runs={history.value ?? []} />
    </>
  );
}
