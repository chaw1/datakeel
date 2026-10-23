import { useEffect, useState } from "react";

import { tablePath } from "../../api/catalog";
import { get } from "../../api/client";
import { ResourceState } from "../../components/ResourceState";
import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";

import { MetricDetails } from "./MetricDetails";

import type {
  CatalogObject,
  CatalogTableDetail,
  ImpactResult,
} from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

export function FilteredMetricCatalog({
  table,
  column,
  onDataChanged,
  onOpenReceipt,
  onCount,
}: {
  table: string;
  column: string;
  onDataChanged?: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
  onCount?: (count: number) => void;
}) {
  const { t, locale } = useI18n();
  const [items, setItems] = useState<CatalogObject[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    const load = table
      ? get<CatalogTableDetail>(tablePath(table)).then((value) => value.metrics)
      : get<ImpactResult>(
          `/api/catalog/neighbors?${new URLSearchParams({ asset_id: column }).toString()}`,
        ).then((value) =>
          value.objects.filter(
            (item) => item.asset_ref.asset_type === "metric",
          ),
        );
    void load
      .then((value) => {
        if (active) {
          setItems(value);
          onCount?.(value.length);
          setLoading(false);
          setError("");
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(String(reason));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [table, column, revision, onCount]);
  return (
    <div className="catalog-browser">
      <section className="card catalog-list" aria-label={t("catMetrics")}>
        <h2>
          {t("pageCount", { name: t("catMetrics"), count: items.length })}
        </h2>
        <p className="mono small">{table || column}</p>
        <a className="text-button" href="#/catalog?kind=metric">
          {t("clearFilter")}
        </a>
        <ResourceState
          loading={loading}
          error={error}
          onRetry={() => {
            setRevision((n) => n + 1);
          }}
        />
        <ul className="catalog-object-list">
          {items.map((item) => (
            <li key={item.asset_ref.asset_id}>
              <button
                onClick={() => {
                  setSelected(item.asset_ref.asset_id);
                }}
              >
                {localizedObjectName(
                  item.asset_ref.asset_type,
                  item.name,
                  locale,
                )}
              </button>
            </li>
          ))}
        </ul>
      </section>
      {selected && (
        <MetricDetails
          key={selected}
          metricId={selected}
          onDataChanged={onDataChanged}
          onOpenReceipt={onOpenReceipt}
        />
      )}
    </div>
  );
}
