import { useState } from "react";

import { catalogPath } from "../../api/catalog";
import { ResourceState } from "../../components/ResourceState";
import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import type {
  CatalogCollection,
  CatalogObject,
  CatalogPage,
} from "../../api/catalog";

export function CatalogList({
  collection,
  label,
  parentId,
  selectedId,
  onSelect,
}: {
  collection: CatalogCollection;
  label: string;
  parentId?: string;
  selectedId?: string;
  onSelect: (item: CatalogObject) => void;
}) {
  const { t, locale } = useI18n();
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const resource = useResource<CatalogPage>(
    catalogPath(collection, offset, search, parentId),
  );
  const page = resource.value;
  return (
    <section className="card catalog-list" aria-label={label}>
      <h2>{label}</h2>
      <input
        type="search"
        aria-label={t("catSearch", { kind: label })}
        placeholder={t("catSearch", { kind: label })}
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
          setOffset(0);
        }}
      />
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {page && !resource.loading && !resource.error && (
        <>
          <ul className="catalog-object-list">
            {page.items.map((item) => (
              <li key={item.asset_ref.asset_id}>
                <button
                  className={
                    selectedId === item.asset_ref.asset_id ? "selected" : ""
                  }
                  aria-pressed={selectedId === item.asset_ref.asset_id}
                  onClick={() => {
                    onSelect(item);
                  }}
                >
                  <strong>
                    {localizedObjectName(
                      item.asset_ref.asset_type,
                      item.name,
                      locale,
                      item.english_name,
                    )}
                  </strong>
                  <span className="mono small">{item.asset_ref.asset_id}</span>
                </button>
              </li>
            ))}
          </ul>
          {!page.items.length && <p className="muted">{t("catEmpty")}</p>}
          <p className="small muted">
            {t("catCount", {
              start: page.items.length ? page.offset + 1 : 0,
              end: page.offset + page.items.length,
              total: page.total,
            })}
          </p>
          <div className="catalog-pagination">
            <button
              className="button subtle"
              disabled={offset === 0}
              onClick={() => {
                setOffset(Math.max(0, offset - 20));
              }}
            >
              {t("previous")}
            </button>
            <button
              className="button subtle"
              disabled={page.offset + page.items.length >= page.total}
              onClick={() => {
                setOffset(offset + 20);
              }}
            >
              {t("next")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
