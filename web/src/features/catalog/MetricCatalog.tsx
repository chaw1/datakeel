import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { CatalogList } from "./CatalogList";
import { MetricDetails } from "./MetricDetails";

import type { CatalogObject } from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

export function MetricCatalog({
  onDataChanged,
  onOpenReceipt,
}: {
  onDataChanged?: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<CatalogObject | null>(null);
  const [revision, setRevision] = useState(0);
  return (
    <div className="catalog-browser">
      <CatalogList
        key={revision}
        collection="metrics"
        label={t("catMetrics")}
        selectedId={selected?.asset_ref.asset_id}
        onSelect={setSelected}
      />
      {selected ? (
        <MetricDetails
          key={selected.asset_ref.asset_id}
          metricId={selected.asset_ref.asset_id}
          onOpenReceipt={onOpenReceipt}
          onDataChanged={() => {
            setRevision((value) => value + 1);
            onDataChanged?.();
          }}
        />
      ) : (
        <div className="card empty-state">{t("catChooseMetric")}</div>
      )}
    </div>
  );
}
