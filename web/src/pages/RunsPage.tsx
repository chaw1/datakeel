import { objectHref } from "../features/object/navigation";
import { StateBadge } from "../features/tasks/StateBadge";
import { TaskOutcome } from "../features/tasks/TaskOutcome";
import { useI18n } from "../i18n/useI18n";
import { date, timestamp } from "../lib/format";

import type { DashboardSnapshot } from "../app/useDashboard";

export function RunsPage({
  data,
  params,
}: {
  data: DashboardSnapshot;
  params: URLSearchParams;
}) {
  const { t } = useI18n();
  const type = params.get("type") ?? "all";
  const active = params.get("state") === "active";
  const rows = [
    ...data.tasks.map((task) => ({
      id: task.id,
      kind: "pipeline",
      name:
        data.datasets.find((dataset) => dataset.id === task.dataset_id)?.name ??
        t("datasetProcessing"),
      state: task.state,
      partial: task.partial,
      created: timestamp(task.created_at),
      completed: task.finished_at === null ? null : timestamp(task.finished_at),
      href: `#/runs?type=pipeline&run=${encodeURIComponent(task.id)}`,
    })),
    ...data.actions.map((run) => ({
      id: run.id,
      kind: "action",
      name: run.action_type,
      state: run.status,
      partial: false,
      created: timestamp(run.created_at),
      completed: run.completed_at ? timestamp(run.completed_at) : null,
      href: objectHref({ kind: "action_run", id: run.id }),
    })),
  ]
    .filter(
      (row) =>
        (type === "all" || row.kind === type) &&
        (!active || ["RUNNING", "QUEUED", "PENDING"].includes(row.state)),
    )
    .sort((a, b) => b.created - a.created || a.id.localeCompare(b.id));
  const task = data.tasks.find((item) => item.id === params.get("run"));
  function filter(nextType: string, nextActive: boolean) {
    const query = new URLSearchParams();
    if (nextType !== "all") query.set("type", nextType);
    if (nextActive) query.set("state", "active");
    window.location.hash = `/runs?${query.toString()}`;
  }
  return (
    <>
      <div className="page-heading">
        <h1>{t("pageCount", { name: t("runRecords"), count: rows.length })}</h1>
      </div>
      <div className="table-toolbar">
        <label>
          {t("runType")}{" "}
          <select
            aria-label={t("runType")}
            value={type}
            onChange={(event) => {
              filter(event.target.value, active);
            }}
            onBlur={(event) => {
              if (event.target.value !== type)
                filter(event.target.value, active);
            }}
          >
            <option value="all">{t("allTypes")}</option>
            <option value="pipeline">{t("pipelineType")}</option>
            <option value="action">{t("actionType")}</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={active}
            onChange={(event) => {
              filter(type, event.target.checked);
            }}
          />
          {t("activeOnly")}
        </label>
      </div>
      <div className="card table-scroll">
        <table aria-label={t("runRecords")}>
          <thead>
            <tr>
              <th>{t("runType")}</th>
              <th>{t("runName")}</th>
              <th>{t("runStatus")}</th>
              <th>{t("scheduledAt")}</th>
              <th>{t("duration")}</th>
              <th>{t("detailsLink")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.kind}:${row.id}`}>
                <td>
                  {t(row.kind === "pipeline" ? "pipelineType" : "actionType")}
                </td>
                <td>{row.name}</td>
                <td>
                  <StateBadge state={row.state} />
                  {row.partial && (
                    <span className="warning-text">
                      {" "}
                      {t("partiallyCompletedShort")}
                    </span>
                  )}
                </td>
                <td>{date(row.created)}</td>
                <td>
                  {row.completed !== null
                    ? t("seconds", {
                        count: Math.max(
                          0,
                          Math.round((row.completed - row.created) / 1000),
                        ),
                      })
                    : "—"}
                </td>
                <td>
                  <a className="text-button" href={row.href}>
                    {t("detailsLink")}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && <p className="empty-state">{t("noMatchingRuns")}</p>}
      {task && (
        <section className="card run-details" aria-label={t("runDetailsTitle")}>
          <h2>{t("runDetailsTitle")}</h2>
          <a
            className="text-button"
            href={objectHref({
              kind: "dataset",
              id: task.dataset_id,
              tab: "history",
            })}
          >
            {t("openDataset")}
          </a>
          <TaskOutcome task={task} />
          <pre>{JSON.stringify(task, null, 2)}</pre>
        </section>
      )}
    </>
  );
}
