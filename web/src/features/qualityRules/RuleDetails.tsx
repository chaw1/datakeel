import { qualityIssuesPath, qualityResultsPath } from "../../api/qualityRules";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date, timestamp } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import { RuleIssues } from "./RuleIssues";
import { resultStatuses, ruleKinds, ruleTarget } from "./ruleLabels";
import { RuleTrend } from "./RuleTrend";
import { useQualityPolling } from "./useQualityPolling";

import type { DqIssue, DqResult, DqRuleView } from "../../api/qualityRules";
import type { ActionPlan } from "../../api/types";

export function RuleDetails({
  view,
  onPrepared,
}: {
  view: DqRuleView;
  onPrepared: (plan: ActionPlan) => void;
}) {
  const { t, locale } = useI18n();
  const results = useResource<DqResult[]>(qualityResultsPath(view.rule.id));
  const issues = useResource<DqIssue[]>(qualityIssuesPath(view.rule.id));
  useQualityPolling(() => {
    results.reload();
    issues.reload();
  });
  const ordered = [...(results.value ?? [])].sort(
    (a, b) => timestamp(b.started_at) - timestamp(a.started_at),
  );
  const latest =
    ordered.find((result) => result.rule_revision === view.rule.revision) ??
    view.latest_result;
  return (
    <section className="card dq-details" aria-label={view.rule.name}>
      <header>
        <div>
          <h2>{view.rule.name}</h2>
          <p className="muted">{ruleTarget(view.rule)}</p>
        </div>
        <span className={`dq-status dq-${latest?.status ?? "pending"}`}>
          {latest ? t(resultStatuses[latest.status]) : t("dqNotRun")}
        </span>
      </header>
      <dl className="dq-meta">
        <div>
          <dt>{t("dqKind")}</dt>
          <dd>{t(ruleKinds[view.rule.kind])}</dd>
        </div>
        <div>
          <dt>{t("dqOwner")}</dt>
          <dd>{view.rule.owner}</dd>
        </div>
        <div>
          <dt>{t("dqSchedule")}</dt>
          <dd>{view.rule.cron ?? t("dqManual")}</dd>
        </div>
        <div>
          <dt>{t("dqThreshold")}</dt>
          <dd>{view.rule.threshold}</dd>
        </div>
      </dl>
      <section aria-label={t("dqTrend")}>
        <h2>{t("dqTrend")}</h2>
        <RuleTrend results={ordered} />
      </section>
      <section aria-label={t("dqResults")}>
        <h2>{t("dqResults")}</h2>
        <ResourceState
          loading={results.loading && !results.value}
          error={results.error}
          onRetry={results.reload}
        />
        {results.value && !ordered.length && (
          <p className="muted">{t("dqNoResults")}</p>
        )}
        {ordered.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("createdAt")}</th>
                  <th>{t("version")}</th>
                  <th>{t("dqStatus")}</th>
                  <th>{t("dqActual")}</th>
                  <th>{t("dqThreshold")}</th>
                  <th>{t("dqRows")}</th>
                  <th>{t("dqCoverage")}</th>
                  <th>{t("dqFailedRows")}</th>
                  <th>{t("dqDuration")}</th>
                </tr>
              </thead>
              <tbody>
                {ordered.map((result) => (
                  <tr key={result.id}>
                    <td>
                      <time dateTime={result.started_at}>
                        {date(result.started_at, locale)}
                      </time>
                    </td>
                    <td>{result.rule_revision}</td>
                    <td>
                      <span className={`dq-status dq-${result.status}`}>
                        {t(resultStatuses[result.status])}
                      </span>
                      {result.message && (
                        <p className="muted">{result.message}</p>
                      )}
                      {Boolean(result.samples.length) && (
                        <details>
                          <summary>{t("dqSamples")}</summary>
                          <pre>{JSON.stringify(result.samples, null, 2)}</pre>
                        </details>
                      )}
                    </td>
                    <td>
                      {result.actual_value == null
                        ? "—"
                        : result.actual_value.toLocaleString(locale)}
                    </td>
                    <td>{result.threshold}</td>
                    <td>{result.rows_scanned}</td>
                    <td>
                      {result.coverage === "complete"
                        ? t("dqCoverageComplete", {
                            scanned: result.rows_scanned,
                            total: result.rows_total ?? 0,
                          })
                        : t("dqCoverageUnknown")}
                    </td>
                    <td>{result.failed_count}</td>
                    <td>
                      {t("dqDurationValue", {
                        value: result.duration_ms.toFixed(1),
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <ResourceState
        loading={issues.loading && !issues.value}
        error={issues.error}
        onRetry={issues.reload}
      />
      {issues.value && (
        <RuleIssues issues={issues.value} onPrepared={onPrepared} />
      )}
    </section>
  );
}
