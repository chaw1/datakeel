import { useState } from "react";

import { catalogPath } from "../../api/catalog";
import { ResourceState } from "../../components/ResourceState";
import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";

import { synonyms, termTarget } from "./values";

import type { CatalogPage } from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

export function Glossary({
  onOpenReceipt,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const resource = useResource<CatalogPage>(
    catalogPath("terms", offset, query),
  );
  const page = resource.value;
  return (
    <section className="card catalog-detail">
      <label className="catalog-glossary-search">
        {t("catSearch", { kind: t("catTerms") })}
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOffset(0);
          }}
        />
      </label>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {page && !resource.loading && !resource.error && (
        <>
          <div className="catalog-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("catTerms")}</th>
                  <th>{t("catSynonyms")}</th>
                  <th>{t("catMeans")}</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((term) => (
                  <tr key={term.asset_ref.asset_id}>
                    <td>
                      <a
                        href={objectHref({
                          kind: "term",
                          id: term.asset_ref.asset_id,
                        })}
                      >
                        <strong>
                          {localizedObjectName("term", term.name, locale)}
                        </strong>
                      </a>
                    </td>
                    <td>{synonyms(term).join(", ") || t("catNotSet")}</td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => {
                          onOpenReceipt({
                            assetId: term.asset_ref.asset_id,
                            includeCatalog: true,
                          });
                        }}
                      >
                        {termTarget(term) || t("catNotSet")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!page.items.length && <p className="muted">{t("catEmpty")}</p>}
          <div className="catalog-pagination">
            <p className="muted small">
              {t("catCount", {
                start: page.items.length ? offset + 1 : 0,
                end: offset + page.items.length,
                total: page.total,
              })}
            </p>
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
              disabled={offset + page.items.length >= page.total}
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
