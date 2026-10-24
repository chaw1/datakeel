import { useState } from "react";

import { KGWorkspace } from "../features/kg/KGWorkspace";
import { useI18n } from "../i18n/useI18n";

import type { Dataset } from "../api/types";
import type { LineageTarget } from "../app/navigation";

export function KnowledgeGraphPage({
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
  const active =
    chosen ||
    datasets.find((item) => item.metadata.kg_samples === true)?.id ||
    datasetId ||
    datasets[0]?.id ||
    "";
  return (
    <div className="kg-page">
      <div className="page-heading">
        <div>
          <h1 className="page-title">{t("kgNav")}</h1>
          <p className="muted">{t("kgIntro")}</p>
        </div>
        <label className="dataset-selector">
          {t("kgDataset")}
          <select
            aria-label={t("kgDataset")}
            value={active}
            onBlur={(event) => {
              setChosen(event.target.value);
            }}
            onChange={(event) => {
              setChosen(event.target.value);
            }}
          >
            {datasets.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {active ? (
        <KGWorkspace
          key={active}
          datasetId={active}
          onDataChanged={onDataChanged}
          onOpenReceipt={onOpenReceipt}
        />
      ) : (
        <section className="card">
          <p>{t("kgNoDataset")}</p>
          <a className="button" href="#/datasets">
            {t("evAddData")}
          </a>
        </section>
      )}
    </div>
  );
}
