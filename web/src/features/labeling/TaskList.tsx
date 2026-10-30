import { useI18n } from "../../i18n/useI18n";

import { stateMessages } from "./model";

import type { ProductionTask, WorkbenchSampleName } from "../../api/production";

export function TaskList({
  tasks,
  samples = [],
  risks,
  onOpen,
}: {
  tasks: ProductionTask[];
  samples?: readonly WorkbenchSampleName[];
  risks: {
    task_id: string;
    prelabel_difference?: number | null;
    model_confidence?: number | null;
  }[];
  onOpen: (task: ProductionTask) => void;
}) {
  const { t } = useI18n();
  const names = new Map(samples.map((item) => [item.task_id, item]));
  if (!tasks.length) return <p className="empty-state">{t("wbNoTasks")}</p>;
  return (
    <div className="table-wrap">
      <table className="wb-task-table" aria-label={t("wbMyTasks")}>
        <thead>
          <tr>
            <th>{t("wbSample")}</th>
            <th>{t("wbState")}</th>
            <th>{t("wbRound")}</th>
            <th>{t("wbConfidence")}</th>
            <th>{t("wbDifference")}</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => {
            const sample = names.get(task.id);
            const name = sample?.name ?? t("wbUnnamedSample");
            return (
              <tr key={task.id}>
                <td>
                  <button
                    type="button"
                    className="text-button"
                    title={sample?.path ?? name}
                    data-task-id={task.id}
                    aria-label={t("wbOpenTask", { id: name })}
                    onClick={() => {
                      onOpen(task);
                    }}
                  >
                    {name}
                  </button>
                </td>
                <td>{t(stateMessages[task.state])}</td>
                <td>{task.round}</td>
                <td>
                  {(risks.find((risk) => risk.task_id === task.id)
                    ?.model_confidence ?? task.confidence) == null
                    ? "—"
                    : `${String(Math.round((risks.find((risk) => risk.task_id === task.id)?.model_confidence ?? task.confidence ?? 0) * 100))}%`}
                </td>
                <td>
                  {risks.find((risk) => risk.task_id === task.id)
                    ?.prelabel_difference == null
                    ? "—"
                    : `${String(Math.round((risks.find((risk) => risk.task_id === task.id)?.prelabel_difference ?? 0) * 100))}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
