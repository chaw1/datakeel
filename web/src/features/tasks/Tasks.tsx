import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { date, taskProgress } from "../../lib/format";

import { StateBadge } from "./StateBadge";

import type { Task } from "../../api/types";
export function Tasks({
  tasks,
  compact = false,
}: {
  tasks: Task[];
  compact?: boolean;
}) {
  const { t, locale } = useI18n();

  if (!tasks.length)
    return (
      <div className="empty-state">
        <Icon name="activity" size={28} />
        <h3>{t("readyForTheFirstRun")}</h3>
        <p>{t("yourPipelineRunsAndLiveProgressWillAppearHere")}</p>
      </div>
    );
  return (
    <div className="task-list">
      {(compact ? tasks.slice(0, 3) : tasks).map((task) => (
        <article className="task-row" key={task.id}>
          <div className="task-icon">
            <Icon name="activity" />
          </div>
          <div className="task-name">
            <strong>{t("datasetProcessing")}</strong>
            <span className="mono">{task.id}</span>
            {task.error && <p className="error-text">{task.error}</p>}
            {task.partial && (
              <p className="warning-text">{t("partiallyCompleted")}</p>
            )}
            {(task.failed_files ?? []).length > 0 && (
              <ul className="task-failures" aria-label={t("failedRecordings")}>
                {(task.failed_files ?? []).map((failure) => (
                  <li key={failure.file_id}>
                    <span className="mono">{failure.filename}</span> ·{" "}
                    {failure.operator}: {failure.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="task-progress">
            <div>
              <span>
                {task.completed_shards} / {task.total_shards}{" "}
                {t("shards", { count: task.total_shards })}{" "}
              </span>
              <strong>{taskProgress(task)}%</strong>
            </div>
            <div className="bar">
              <span style={{ width: `${String(taskProgress(task))}%` }} />
            </div>
          </div>
          <StateBadge state={task.state} />
          <span className="task-date">{date(task.created_at, locale)}</span>
        </article>
      ))}
    </div>
  );
}
