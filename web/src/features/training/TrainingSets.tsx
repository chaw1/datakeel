import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { TrainingWorkspace } from "./TrainingWorkspace";
import "./training.css";

import type { Version } from "../../api/types";

export function TrainingSets({
  datasetId,
  versions,
}: {
  datasetId: string;
  versions: Version[];
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState(versions.at(0)?.id ?? "");
  const versionId = versions.some((version) => version.id === selected)
    ? selected
    : (versions.at(0)?.id ?? "");
  return (
    <section className="training-sets" aria-label={t("trainingTitle")}>
      <div className="card-heading">
        <div>
          <h3>{t("trainingTitle")}</h3>
          <p>{t("trainingDescription")}</p>
        </div>
      </div>
      {versionId ? (
        <>
          <div className="training-controls">
            <label>
              {t("trainingVersion")}
              <select
                value={versionId}
                onBlur={(event) => {
                  setSelected(event.target.value);
                }}
                onChange={(event) => {
                  setSelected(event.target.value);
                }}
              >
                {versions.map((version) => (
                  <option key={version.id} value={version.id}>
                    {version.id}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <TrainingWorkspace
            key={versionId}
            datasetId={datasetId}
            versionId={versionId}
          />
        </>
      ) : (
        <p className="empty-state">{t("trainingNoVersions")}</p>
      )}
    </section>
  );
}
