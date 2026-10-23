import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { StateBadge } from "../tasks/StateBadge";

import { stepLabel, workflowName } from "./labels";

import type { WorkflowRun } from "../../api/workflows";

export function WorkflowTimeline({
  run,
  busy,
  onResume,
}: {
  run: WorkflowRun;
  busy: boolean;
  onResume: () => void;
}) {
  const { t, locale } = useI18n();
  return (
    <section
      className="card workflow-run"
      aria-label={t("runDetails")}
      data-run-id={run.id}
      data-run-status={run.status}
    >
      <header className="workflow-run-heading">
        <div>
          <span className="eyebrow">{t("runDetails")}</span>
          <h2>{workflowName(run.workflow_id, t)}</h2>
        </div>
        <StateBadge state={run.status} />
      </header>
      <dl className="detail-grid">
        <div>
          <dt>{t("runId")}</dt>
          <dd>
            <code>{run.id}</code>
          </dd>
        </div>
        <div>
          <dt>{t("createdAt")}</dt>
          <dd>{date(run.created_at, locale)}</dd>
        </div>
      </dl>
      {run.error && (
        <p className="error-banner" role="alert">
          {run.error}
        </p>
      )}
      {run.status === "INTERRUPTED" && (
        <p className="muted">{t("workflowInterruptedHint")}</p>
      )}
      {run.status === "PAUSED" && run.pending_plan_id && (
        <div className="workflow-approval" role="status">
          <strong>{t("workflowPaused")}</strong>
          <p>{t("workflowApprovalHint")}</p>
          <div className="workflow-actions">
            <a
              className="button"
              href={`#/approvals?${new URLSearchParams({ plan: run.pending_plan_id, workflow_run: run.id }).toString()}`}
            >
              {t("workflowApproval")}
            </a>
            <button
              className="button primary"
              disabled={busy}
              onClick={onResume}
            >
              {t("workflowResume")}
            </button>
          </div>
        </div>
      )}
      <h3>{t("workflowSteps")}</h3>
      <ol className="workflow-timeline">
        {run.steps.map((step, index) => {
          const output =
            step.output === null || step.output === undefined
              ? ""
              : typeof step.output === "string"
                ? step.output
                : JSON.stringify(step.output);
          return (
            <li
              key={step.id}
              data-step-id={step.id}
              data-step-status={step.status}
            >
              <span className="workflow-step-number">{index + 1}</span>
              <div className="workflow-step-body">
                <div className="workflow-step-heading">
                  <div>
                    <strong>{stepLabel(step.type, t)}</strong>{" "}
                    <code>{step.id}</code>
                  </div>
                  <StateBadge state={step.status} />
                </div>
                {step.error && (
                  <p className="error-text" role="alert">
                    {step.error}
                  </p>
                )}
                {output && (
                  <>
                    <p
                      className="workflow-output-summary"
                      aria-label={t("workflowOutputSummary")}
                    >
                      {output.length > 220
                        ? `${output.slice(0, 220)}…`
                        : output}
                    </p>
                    <details>
                      <summary>{t("workflowOutput")}</summary>
                      <pre>{JSON.stringify(step.output, null, 2)}</pre>
                    </details>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
