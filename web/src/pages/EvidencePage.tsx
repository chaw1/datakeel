import { useState } from "react";

import { EvidenceExplorer } from "../features/evidence/EvidenceExplorer";
import { useI18n } from "../i18n/useI18n";

import type { Dataset } from "../api/types";
import type { LineageTarget } from "../app/navigation";

export function EvidencePage({
  datasets,
  datasetId,
  onDataChanged,
  onOpenReceipt,
}: {
  datasets: Dataset[];
  datasetId: string;
  onDataChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [chosen, setChosen] = useState("");
  const [count, setCount] = useState(0);
  const preferred = datasets.find(
    (item) => item.metadata.evidence_samples === true,
  )?.id;
  const active = chosen || preferred || datasetId || datasets[0]?.id || "";
  return (
    <div className="evidence-page">
      <div className="page-heading evidence-page-heading">
        <h1 className="page-title">{t("evTitle", { count })}</h1>
        <label className="dataset-selector">
          {t("evDataset")}
          <select
            value={active}
            onBlur={(event) => {
              if (active !== event.target.value) setChosen(event.target.value);
            }}
            onChange={(event) => {
              setChosen(event.target.value);
            }}
          >
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {active ? (
        <EvidenceExplorer
          key={active}
          datasetId={active}
          onDataChanged={onDataChanged}
          onOpenReceipt={onOpenReceipt}
          dataset={datasets.find((item) => item.id === active)}
          onCount={setCount}
        />
      ) : (
        <div className="card evidence-empty" data-empty-kind="data">
          <h3>{t("evNoData")}</h3>
          <a className="button" href="#/datasets">
            {t("evAddData")}
          </a>
        </div>
      )}
    </div>
  );
}
