import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { StateBadge } from "../tasks/StateBadge";

import { workflowHref, workflowName } from "./labels";

import type { WorkflowRun } from "../../api/workflows";

export function WorkflowHistory({ runs }: { runs: WorkflowRun[] }) {
  const { t, locale } = useI18n();
  return (
    <section
      className="card workflow-history"
      aria-label={t("workflowHistory")}
    >
      <h2>{t("workflowHistory")}</h2>
      {!runs.length ? (
        <p className="muted">{t("workflowNoRuns")}</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t("workflowsNav")}</th>
                <th>{t("runId")}</th>
                <th>{t("workflowStatus")}</th>
                <th>{t("createdAt")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <a href={workflowHref(run.id)}>
                      {workflowName(run.workflow_id, t)}
                    </a>
                  </td>
                  <td>
                    <code title={run.id}>{run.id.slice(0, 8)}</code>
                  </td>
                  <td>
                    <StateBadge state={run.status} />
                  </td>
                  <td>{date(run.created_at, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
