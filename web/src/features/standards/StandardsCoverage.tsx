import { useState } from "react";

import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";

import { percentage, ruleLabels } from "./values";

import type { StandardsCoverage as Coverage } from "../../api/standards";

const groups = [
  ["sources", "stdDatabase"],
  ["tables", "stdTable"],
  ["owners", "stdOwner"],
] as const;
export function StandardsCoverage() {
  const { t } = useI18n();
  const resource = useResource<Coverage>("/api/standards/coverage");
  const [group, setGroup] = useState<(typeof groups)[number][0]>("tables");
  const coverage = resource.value;
  return (
    <section className="card standards-section">
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {coverage && (
        <>
          <dl className="standards-summary">
            <div>
              <dt>{t("stdTotalColumns")}</dt>
              <dd>{coverage.overall.total_columns}</dd>
            </div>
            <div>
              <dt>{t("stdCoverageRate")}</dt>
              <dd>{percentage(coverage.overall.coverage)}</dd>
            </div>
            <div>
              <dt>{t("stdComplianceRate")}</dt>
              <dd>{percentage(coverage.overall.compliance)}</dd>
            </div>
          </dl>
          <label>
            {t("stdGroupBy")}
            <select
              value={group}
              onBlur={(event) => {
                const selected = groups.find(
                  ([key]) => key === event.target.value,
                )?.[0];
                if (selected) setGroup(selected);
              }}
              onChange={(event) => {
                const selected = groups.find(
                  ([key]) => key === event.target.value,
                )?.[0];
                if (selected) setGroup(selected);
              }}
            >
              {groups.map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>
          <div className="catalog-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>
                    {t(
                      groups.find(([key]) => key === group)?.[1] ?? "stdTable",
                    )}
                  </th>
                  <th>{t("stdTotalColumns")}</th>
                  <th>{t("stdMappedColumns")}</th>
                  <th>{t("stdCoverageRate")}</th>
                  <th>{t("stdComplianceRate")}</th>
                </tr>
              </thead>
              <tbody>
                {coverage[group].map((item) => (
                  <tr key={item.key}>
                    <td>
                      {group === "tables" ? (
                        <a
                          href={objectHref({
                            kind: "table",
                            id: item.key,
                            tab: "facts",
                          })}
                        >
                          {item.key}
                        </a>
                      ) : (
                        item.key || t("catNotSet")
                      )}
                    </td>
                    <td>{item.total_columns}</td>
                    <td>{item.mapped_columns}</td>
                    <td>{percentage(item.coverage)}</td>
                    <td>{percentage(item.compliance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h2>
            {t("stdTopViolations", {
              count: coverage.violation_top.length,
            })}
          </h2>
          {coverage.violation_top.length ? (
            <div className="catalog-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("stdColumn")}</th>
                    <th>{t("stdStandard")}</th>
                    <th>{t("stdViolationCount")}</th>
                    <th>{t("stdRules")}</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.violation_top.map((item) => (
                    <tr key={item.column_id}>
                      <td>
                        <a
                          href={objectHref({
                            kind: "column",
                            id: item.column_id,
                            tab: "facts",
                          })}
                        >
                          {item.column_id}
                        </a>
                      </td>
                      <td>{item.standard_code}</td>
                      <td>{item.violation_count}</td>
                      <td>
                        {item.rules
                          .map((rule) => t(ruleLabels[rule]))
                          .join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>{t("stdNoViolations")}</p>
          )}
        </>
      )}
    </section>
  );
}
