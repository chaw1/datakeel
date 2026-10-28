import { standardsReportPath } from "../../api/standards";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import { percentage, ruleLabels } from "./values";

import type { StandardsReport } from "../../api/standards";

export function StandardsChecks({
  tableId,
  columnId,
}: {
  tableId: string;
  columnId?: string;
}) {
  const { t } = useI18n();
  const resource = useResource<StandardsReport>(standardsReportPath(tableId));
  const report = resource.value;
  const checks = (
    report && Array.isArray(report.checks) ? report.checks : []
  ).filter((item) => !columnId || item.column_id === columnId);
  return (
    <section className="standards-checks" aria-label={t("stdChecks")}>
      <div className="section-heading">
        <h2>{t("stdChecks")}</h2>
        <a href="#/standards">{t("stdViewAll")}</a>
      </div>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {report?.coverage && (
        <p>
          {t("stdCoverageRate")}: {percentage(report.coverage.overall.coverage)}{" "}
          · {t("stdComplianceRate")}:{" "}
          {percentage(report.coverage.overall.compliance)}
        </p>
      )}
      {checks.map((check) => (
        <details key={check.column_id}>
          <summary>
            <strong>{check.column_id.split("/").at(-1)}</strong> ·{" "}
            {check.standard_code} ·{" "}
            <span
              className={`badge ${check.compliant && check.fully_checked ? "green" : "amber"}`}
            >
              {t(
                check.compliant
                  ? check.fully_checked
                    ? "stdCompliant"
                    : "stdPartial"
                  : "stdNotCompliant",
              )}
            </span>
          </summary>
          {check.skipped_rules.length > 0 && (
            <p className="muted">
              {t("stdSkippedRules")}: {check.skipped_rules.join(", ")}
            </p>
          )}
          {check.violations.length > 0 && (
            <div className="catalog-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("stdRule")}</th>
                    <th>{t("stdViolationCount")}</th>
                    <th>{t("stdDefinition")}</th>
                    <th>{t("stdSamples")}</th>
                  </tr>
                </thead>
                <tbody>
                  {check.violations.map((item) => (
                    <tr key={item.rule}>
                      <td>{t(ruleLabels[item.rule])}</td>
                      <td>{item.count}</td>
                      <td>{item.message}</td>
                      <td>{item.samples.join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </details>
      ))}
      {!resource.loading && !resource.error && !checks.length && (
        <p className="muted">{t("stdUnmapped")}</p>
      )}
    </section>
  );
}
