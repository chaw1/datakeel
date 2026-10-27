import { useState } from "react";

import { CatalogBrowser } from "../features/catalog/CatalogBrowser";
import { FilteredMetricCatalog } from "../features/catalog/FilteredMetricCatalog";
import { Glossary } from "../features/catalog/Glossary";
import { ImportedObjects } from "../features/catalog/ImportedObjects";
import { MetadataImportForm } from "../features/catalog/MetadataImportForm";
import { MetricCatalog } from "../features/catalog/MetricCatalog";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { CatalogPage as CatalogResult } from "../api/catalog";
import type { LineageTarget } from "../app/navigation";

import "../features/catalog/catalog.css";

const tabs = [
  ["tables", "catBrowse"],
  ["metrics", "catMetrics"],
  ["terms", "catTerms"],
  ["imports", "metadataImports"],
] as const;

export function CatalogPage({
  onOpenReceipt,
  onDataChanged,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
  onDataChanged?: () => void;
}) {
  const { t } = useI18n();
  const params = new URLSearchParams(window.location.hash.split("?")[1]);
  const initial = params.get("kind");
  const [chosen, setTab] = useState<(typeof tabs)[number][0] | null>(null);
  const [importRevision, setImportRevision] = useState(0);
  const [filteredCount, setFilteredCount] = useState(0);
  const tab =
    chosen ??
    (initial === "imports"
      ? "imports"
      : initial === "metric"
        ? "metrics"
        : initial === "term"
          ? "terms"
          : "tables");
  const count = useResource<CatalogResult>(
    `/api/catalog/${tab === "imports" ? "import/objects" : tab}?limit=1`,
  );
  const table = params.get("table") ?? "";
  const column = params.get("column") ?? "";
  return (
    <div className="catalog-page">
      <div className="page-heading">
        <div>
          <h1>
            {t("pageCount", {
              name: t("catalogNav"),
              count:
                tab === "metrics" && (table || column)
                  ? filteredCount
                  : (count.value?.total ?? 0),
            })}
          </h1>
        </div>
      </div>
      <nav className="tabs" aria-label={t("catalogNav")}>
        {tabs.map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? "active" : ""}
            aria-current={tab === value ? "page" : undefined}
            onClick={() => {
              setTab(value);
            }}
          >
            {t(label)}
          </button>
        ))}
      </nav>
      {tab === "imports" && (
        <>
          <MetadataImportForm
            onImported={() => {
              setImportRevision((value) => value + 1);
              count.reload();
              onDataChanged?.();
            }}
          />
          <ImportedObjects key={importRevision} onOpenReceipt={onOpenReceipt} />
        </>
      )}
      {tab === "tables" && <CatalogBrowser onOpenReceipt={onOpenReceipt} />}
      {tab === "metrics" && (table || column) ? (
        <FilteredMetricCatalog
          table={table}
          column={column}
          onDataChanged={onDataChanged}
          onOpenReceipt={onOpenReceipt}
          onCount={setFilteredCount}
        />
      ) : (
        tab === "metrics" && (
          <MetricCatalog
            onOpenReceipt={onOpenReceipt}
            onDataChanged={onDataChanged}
          />
        )
      )}
      {tab === "terms" && <Glossary onOpenReceipt={onOpenReceipt} />}
    </div>
  );
}
