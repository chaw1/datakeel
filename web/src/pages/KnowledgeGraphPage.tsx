import { useState } from "react";

import { PageHeader, Select, Surface } from "../components/ui";
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
    datasets.find(
      (item) =>
        item.metadata.kg_samples === true &&
        item.metadata.image_kg_samples !== true,
    )?.id ||
    datasetId ||
    datasets[0]?.id ||
    "";
  return (
    <div className="kg-page">
      <PageHeader
        titleClassName="page-title"
        title={t("kgNav")}
        subtitle={t("kgIntro")}
        actions={
          <label className="dataset-selector">
            {t("kgDataset")}
            <Select
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
            </Select>
          </label>
        }
      />
      {active ? (
        <KGWorkspace
          key={active}
          datasetId={active}
          onDataChanged={onDataChanged}
          onOpenReceipt={onOpenReceipt}
        />
      ) : (
        <Surface as="section">
          <p>{t("kgNoDataset")}</p>
          <a className="button ui-button" href="#/datasets">
            {t("evAddData")}
          </a>
        </Surface>
      )}
    </div>
  );
}
