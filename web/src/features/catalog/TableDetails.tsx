import { useState } from "react";

import { tablePath } from "../../api/catalog";
import { ResourceState } from "../../components/ResourceState";
import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";
import { StandardsChecks } from "../standards/StandardsChecks";

import { ImpactTree } from "./ImpactTree";
import { linkLabels, propertyText } from "./values";

import type { CatalogTableDetail } from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

export function TableDetails({
  tableId,
  onOpenReceipt,
}: {
  tableId: string;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const [fieldId, setFieldId] = useState("");
  const resource = useResource<CatalogTableDetail>(tablePath(tableId));
  const detail = resource.value;
  return (
    <section className="card catalog-detail" aria-label={t("catFields")}>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {detail && !resource.loading && !resource.error && (
        <>
          <div className="section-heading">
            <div>
              <h2>{localizedObjectName("table", detail.table.name, locale)}</h2>
              <a
                className="text-button"
                href={objectHref({ kind: "table", id: tableId })}
              >
                {t("objOpen")}
              </a>
              <p className="mono small muted">
                {detail.table.asset_ref.asset_id}
              </p>
            </div>
            <button
              className="button subtle"
              onClick={() => {
                onOpenReceipt({ assetId: tableId, includeCatalog: true });
              }}
            >
              {t("catLineage")}
            </button>
          </div>
          <p>
            <strong>{t("catOwner")}</strong>
            {": "}
            {detail.owners
              .map((item) => localizedObjectName("owner", item.name, locale))
              .join(", ") || t("catNotSet")}
          </p>
          <div className="catalog-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("catFields")}</th>
                  <th>{t("catFieldType")}</th>
                  <th>{t("catKey")}</th>
                  <th>{t("catNullable")}</th>
                  <th>{t("catImpact")}</th>
                </tr>
              </thead>
              <tbody>
                {detail.columns.map((column) => (
                  <tr key={column.asset_ref.asset_id}>
                    <td>
                      <a
                        href={objectHref({
                          kind: "column",
                          id: column.asset_ref.asset_id,
                        })}
                      >
                        <strong>
                          {localizedObjectName("column", column.name, locale)}
                        </strong>
                      </a>
                    </td>
                    <td className="mono">
                      {propertyText(column, "data_type")}
                    </td>
                    <td>
                      {t(
                        column.properties?.primary_key === true ? "yes" : "no",
                      )}
                    </td>
                    <td>
                      {t(column.properties?.nullable === true ? "yes" : "no")}
                    </td>
                    <td>
                      <button
                        className="text-button"
                        aria-label={`${t("catImpact")}: ${localizedObjectName("column", column.name, locale)}`}
                        onClick={() => {
                          setFieldId(column.asset_ref.asset_id);
                        }}
                      >
                        {t("catImpact")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {fieldId && (
            <ImpactTree
              key={fieldId}
              assetId={fieldId}
              onOpenReceipt={onOpenReceipt}
            />
          )}
          <section>
            <h3>{t("catUsesTable")}</h3>
            {detail.metrics.length ? (
              <ul className="catalog-consumers">
                {detail.metrics.map((metric) => (
                  <li key={metric.asset_ref.asset_id}>
                    <button
                      className="text-button"
                      onClick={() => {
                        onOpenReceipt({
                          assetId: metric.asset_ref.asset_id,
                          includeCatalog: true,
                        });
                      }}
                    >
                      {localizedObjectName("metric", metric.name, locale)}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">{t("catEmpty")}</p>
            )}
          </section>
          <StandardsChecks tableId={tableId} />
          <details>
            <summary>{t("catRelationships")}</summary>
            {detail.neighbors.links.length ? (
              <ul className="catalog-relations">
                {detail.neighbors.links.map((link) => (
                  <li
                    key={`${link.kind}:${link.source.asset_id}:${link.target.asset_id}`}
                  >
                    <code>{link.source.asset_id}</code>
                    <span>{t(linkLabels[link.kind])}</span>
                    <code>{link.target.asset_id}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">{t("catNoRelations")}</p>
            )}
          </details>
        </>
      )}
    </section>
  );
}
