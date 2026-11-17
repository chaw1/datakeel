import { useState } from "react";

import { ResourceState } from "../../components/ResourceState";
import { Button, Select, Surface } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import { MetadataEvidence } from "./MetadataEvidence";
import { MetricDraftConfirmation } from "./MetricDraftConfirmation";

import type { CatalogObject, CatalogPage } from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

const kinds = [
  ["", "metadataAllKinds"],
  ["table", "catTableType"],
  ["column", "catColumnType"],
  ["dag", "metadataDag"],
  ["airflow_task", "metadataTask"],
  ["exposure", "metadataExposure"],
  ["metric_draft", "metadataDraft"],
  ["job", "metadataJob"],
] as const;

export function ImportedObjects({
  onOpenReceipt,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [kind, setKind] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<CatalogObject | null>(null);
  const query = new URLSearchParams({ limit: "20", offset: String(offset) });
  if (kind) query.set("kind", kind);
  const resource = useResource<CatalogPage>(
    `/api/catalog/import/objects?${query.toString()}`,
  );
  return (
    <Surface
      as="section"
      className="catalog-detail"
      aria-label={t("metadataImportedObjects")}
    >
      <div className="section-heading">
        <h2>{t("metadataImportedObjects")}</h2>
        <Button variant="ghost" onClick={resource.reload}>
          {t("metadataRefresh")}
        </Button>
      </div>
      <label>
        {t("metadataKind")}
        <Select
          value={kind}
          onBlur={(event) => {
            setKind(event.target.value);
          }}
          onChange={(event) => {
            setKind(event.target.value);
            setOffset(0);
            setSelected(null);
          }}
        >
          {kinds.map(([value, label]) => (
            <option key={value} value={value}>
              {t(label)}
            </option>
          ))}
        </Select>
      </label>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {resource.value && !resource.loading && (
        <>
          <ul className="catalog-object-list">
            {resource.value.items.map((item) => (
              <li key={item.asset_ref.asset_id}>
                <button
                  className={
                    selected?.asset_ref.asset_id === item.asset_ref.asset_id
                      ? "selected"
                      : ""
                  }
                  onClick={() => {
                    setSelected(item);
                  }}
                >
                  <strong>{item.name}</strong>
                  <span>{item.asset_ref.asset_type}</span>
                </button>
              </li>
            ))}
          </ul>
          {!resource.value.items.length && <p>{t("catEmpty")}</p>}
          <div className="catalog-pagination">
            <Button
              variant="ghost"
              disabled={!offset}
              onClick={() => {
                setOffset(Math.max(0, offset - 20));
              }}
            >
              {t("previous")}
            </Button>
            <span>{resource.value.total}</span>
            <Button
              variant="ghost"
              disabled={offset + 20 >= resource.value.total}
              onClick={() => {
                setOffset(offset + 20);
              }}
            >
              {t("next")}
            </Button>
          </div>
        </>
      )}
      {selected && (
        <section className="catalog-editor">
          <h3>{selected.name}</h3>
          <code>{selected.asset_ref.asset_id}</code>
          <MetadataEvidence item={selected} />
          {selected.asset_ref.asset_type === "metric_draft" && (
            <MetricDraftConfirmation
              key={`${selected.asset_ref.asset_id}:${String(selected.revision)}`}
              item={selected}
              onChanged={resource.reload}
              onOpenReceipt={onOpenReceipt}
            />
          )}
          <Button
            variant="ghost"
            onClick={() => {
              onOpenReceipt({
                assetId: selected.asset_ref.asset_id,
                includeCatalog: true,
              });
            }}
          >
            {t("catLineage")}
          </Button>
        </section>
      )}
    </Surface>
  );
}
