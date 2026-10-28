import { useI18n } from "../../i18n/useI18n";

import type { CatalogObject } from "../../api/catalog";
import type { MessageKey } from "../../i18n/en";

const typeLabels: Partial<Record<string, MessageKey>> = {
  empty: "objProfileTypeEmpty",
  boolean: "objProfileTypeBoolean",
  integer: "objProfileTypeInteger",
  number: "objProfileTypeNumber",
  amount: "objProfileTypeAmount",
  date: "objProfileTypeDate",
  datetime: "objProfileTypeDatetime",
  identifier: "objProfileTypeIdentifier",
  enum: "objProfileTypeEnum",
  string: "objProfileTypeString",
};

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function rate(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(1)}%`
    : "—";
}

function typeText(
  value: unknown,
  translate: (key: MessageKey) => string,
): string {
  const key = typeof value === "string" ? typeLabels[value] : undefined;
  return key ? translate(key) : "—";
}

function summary(value: unknown): string {
  const distribution = record(value);
  const numeric = record(distribution?.numeric);
  if (
    typeof numeric?.minimum === "number" &&
    typeof numeric.maximum === "number"
  )
    return `${numeric.minimum.toLocaleString()} – ${numeric.maximum.toLocaleString()}`;
  const categories: unknown[] = Array.isArray(distribution?.top_values)
    ? distribution.top_values
    : [];
  return (
    categories
      .flatMap((item) => {
        const category = record(item);
        return category && typeof category.value === "string"
          ? [`${category.value} (${String(category.count)})`]
          : [];
      })
      .join(", ") || "—"
  );
}

export function ObjectProfile({
  object,
}: {
  object: CatalogObject | undefined;
}) {
  const { t } = useI18n();
  const table = record(object?.properties?.table_profile);
  const column = record(object?.properties?.profile);
  const values: unknown[] = Array.isArray(table?.columns)
    ? table.columns
    : column
      ? [column]
      : [];
  const columns = values.flatMap((value) => {
    const item = record(value);
    return item && typeof item.name === "string" ? [item] : [];
  });
  const foreign: unknown[] = Array.isArray(table?.foreign_keys)
    ? table.foreign_keys
    : [];
  const candidates = foreign.flatMap((value) => {
    const item = record(value);
    return item && typeof item.column === "string" ? [item] : [];
  });
  if (!columns.length) return null;
  return (
    <section aria-label={t("objTableProfile")}>
      <h3>{t("objTableProfile")}</h3>
      {typeof table?.row_count === "number" && (
        <p>
          {t("objProfileRows")}: {table.row_count}
        </p>
      )}
      <p>{t("objProfileInferred")}</p>
      <div className="catalog-table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("catFields")}</th>
              <th>{t("objDataType")}</th>
              <th>{t("objProfileNullRate")}</th>
              <th>{t("objProfileUniqueRate")}</th>
              <th>{t("objProfilePrimaryKey")}</th>
              <th>{t("objProfilePii")}</th>
              <th>{t("objProfileDistribution")}</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((item) => (
              <tr key={String(item.name)}>
                <th scope="row">{String(item.name)}</th>
                <td>{typeText(item.inferred_type, t)}</td>
                <td>{rate(item.null_rate)}</td>
                <td>{rate(item.unique_rate)}</td>
                <td>{t(item.primary_key_candidate === true ? "yes" : "no")}</td>
                <td>
                  {Array.isArray(item.pii_kinds) && item.pii_kinds.length
                    ? item.pii_kinds
                        .map((kind: unknown) =>
                          kind === "phone"
                            ? t("objProfilePhone")
                            : kind === "email"
                              ? t("objProfileEmail")
                              : String(kind),
                        )
                        .join(", ")
                    : t("no")}
                </td>
                <td>{summary(item.distribution)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {candidates.length > 0 && (
        <details>
          <summary>{t("objProfileForeignKeys")}</summary>
          <ul>
            {candidates.map((item) => (
              <li
                key={`${String(item.column)}:${String(item.referenced_file)}:${String(item.referenced_column)}`}
              >
                {String(item.column)} → {String(item.referenced_file)}.
                {String(item.referenced_column)} ({rate(item.coverage)})
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
