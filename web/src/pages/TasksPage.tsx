import { Surface } from "../components/ui";
import { Tasks } from "../features/tasks/Tasks";
import { useI18n } from "../i18n/useI18n";

import type { DatasetData } from "../api/types";

export function TasksPage({ data }: { data: DatasetData }) {
  const { t } = useI18n();
  return (
    <Surface as="section">
      <div className="card-heading">
        <h2>{t("runHistory")}</h2>
        <span className="muted small">{t("updatesEvery5Seconds")}</span>
      </div>
      <Tasks tasks={data.tasks} />
    </Surface>
  );
}
