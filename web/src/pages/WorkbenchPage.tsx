import { objectHref } from "../features/object/navigation";
import { useI18n } from "../i18n/useI18n";
import { date, timestamp } from "../lib/format";
import { useClock } from "../lib/useClock";

import type { DashboardSnapshot } from "../app/useDashboard";

export function WorkbenchPage({ data }: { data: DashboardSnapshot }) {
  const { t } = useI18n();
  const now = useClock();
  const running = data.tasks.filter((task) =>
    ["RUNNING", "PENDING", "QUEUED"].includes(task.state),
  );
  const alerts = data.datasets.filter(
    (dataset) => dataset.quality_score != null && dataset.quality_score < 60,
  );
  const recent = [...data.actions]
    .sort((a, b) => timestamp(b.created_at) - timestamp(a.created_at))
    .slice(0, 5);
  return (
    <>
      <div className="page-heading">
        <h1 className="page-title">
          {t("workbenchCount", {
            count: data.approvals.length + running.length + alerts.length,
          })}
        </h1>
      </div>
      <div className="workbench-grid">
        <section className="card workbench-section" data-workbench="approvals">
          <header>
            <h2>{t("pendingCount", { count: data.approvals.length })}</h2>
            <a className="text-button" href="#/approvals?status=pending">
              {t("workbenchReview")}
            </a>
          </header>
          <ul>
            {data.approvals.slice(0, 5).map((plan) => (
              <li key={plan.id}>
                <a href={`#/approvals?plan=${encodeURIComponent(plan.id)}`}>
                  {plan.action_type}
                </a>
                <span>
                  {new Date(plan.expires_at).getTime() <= now
                    ? t("expiredLabel")
                    : t("remainingMinutes", {
                        count: Math.ceil(
                          (new Date(plan.expires_at).getTime() - now) / 60_000,
                        ),
                      })}
                </span>
              </li>
            ))}
          </ul>
          {!data.approvals.length && (
            <p className="muted">{t("noCurrentWork")}</p>
          )}
        </section>
        <section className="card workbench-section" data-workbench="runs">
          <header>
            <h2>{t("runningPipelines", { count: running.length })}</h2>
            <a className="text-button" href="#/runs?type=pipeline&state=active">
              {t("workbenchRuns")}
            </a>
          </header>
          <ul>
            {running.slice(0, 5).map((task) => (
              <li key={task.id}>
                <a
                  href={`#/runs?type=pipeline&run=${encodeURIComponent(task.id)}`}
                >
                  {data.datasets.find(
                    (dataset) => dataset.id === task.dataset_id,
                  )?.name ?? t("datasetProcessing")}
                </a>
                <span>{task.progress}%</span>
              </li>
            ))}
          </ul>
          {!running.length && <p className="muted">{t("noCurrentWork")}</p>}
          <h3>{t("recentActions")}</h3>
          <ul>
            {recent.map((run) => (
              <li key={run.id}>
                <a href={objectHref({ kind: "action_run", id: run.id })}>
                  {run.action_type}
                </a>
                <time>{date(run.created_at)}</time>
              </li>
            ))}
          </ul>
        </section>
        <section className="card workbench-section" data-workbench="quality">
          <header>
            <h2>{t("qualityAlerts", { count: alerts.length })}</h2>
            <a className="text-button" href="#/quality?filter=alerts">
              {t("workbenchQuality")}
            </a>
          </header>
          <ul>
            {alerts.map((dataset) => (
              <li key={dataset.id}>
                <a
                  href={objectHref({
                    kind: "dataset",
                    id: dataset.id,
                    tab: "quality",
                  })}
                >
                  {dataset.name}
                </a>
                <span>{dataset.quality_score?.toFixed(1)}</span>
              </li>
            ))}
          </ul>
          {!alerts.length && <p className="muted">{t("noQualityAlerts")}</p>}
        </section>
      </div>
    </>
  );
}
