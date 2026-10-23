import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { CatalogList } from "./CatalogList";
import { TableDetails } from "./TableDetails";

import type { CatalogObject } from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

export function CatalogBrowser({
  onOpenReceipt,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [source, setSource] = useState<CatalogObject | null>(null);
  const [table, setTable] = useState<CatalogObject | null>(null);
  return (
    <div className="catalog-browser">
      <aside className="catalog-source-tree" aria-label={t("catBrowse")}>
        <CatalogList
          collection="sources"
          label={t("catSources")}
          selectedId={source?.asset_ref.asset_id}
          onSelect={(item) => {
            setSource(item);
            setTable(null);
          }}
        />
        {source && (
          <div className="catalog-nested-tables">
            <p className="eyebrow">{t("catSelected", { name: source.name })}</p>
            <CatalogList
              key={source.asset_ref.asset_id}
              collection="tables"
              label={t("catTables")}
              parentId={source.asset_ref.asset_id}
              selectedId={table?.asset_ref.asset_id}
              onSelect={setTable}
            />
          </div>
        )}
      </aside>
      {table ? (
        <TableDetails
          key={table.asset_ref.asset_id}
          tableId={table.asset_ref.asset_id}
          onOpenReceipt={onOpenReceipt}
        />
      ) : (
        <div className="card empty-state">
          <p>{t(source ? "catChooseTable" : "catChooseSource")}</p>
        </div>
      )}
    </div>
  );
}
