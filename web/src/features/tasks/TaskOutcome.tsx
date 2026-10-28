import { useI18n } from "../../i18n/useI18n";

import type { Task } from "../../api/types";

export function TaskOutcome({ task }: { task: Task }) {
  const { t } = useI18n();
  const failures = task.failed_files ?? [];
  return (
    <>
      {task.partial && (
        <p className="warning-text">{t("partiallyCompleted")}</p>
      )}
      {failures.length > 0 && (
        <ul className="task-failures" aria-label={t("failedRecordings")}>
          {failures.map((failure) => (
            <li key={failure.file_id}>
              <span className="mono">{failure.filename}</span> ·{" "}
              {failure.operator}: {failure.reason}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
