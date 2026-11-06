import { useI18n } from "../../i18n/useI18n";

import type { VectorQueryResult } from "../../api/types";

export function VectorReport({ result }: { result: VectorQueryResult }) {
  const { t } = useI18n();
  const report = result.report;
  return (
    <section aria-label={t("vecReport")}>
      <p role="status">
        {t("vecReport")}: {t(`vecStatus_${report.status}`)} ·{" "}
        {t(`vecState_${result.status}`)}
      </p>
      <p>{report.reason || result.reason}</p>
      <p>{t("vecFake")}</p>
      <dl>
        <dt>{t("vecRun")}</dt>
        <dd>
          <code>{result.run_id}</code> · {t(`vecKind_${result.kind}`)}
        </dd>
        <dt>{t("vecSnapshot")}</dt>
        <dd>
          <code>{result.snapshot}</code>
        </dd>
        <dt>{t("vecReferences")}</dt>
        <dd>
          <code>{result.reference_digest}</code>
        </dd>
      </dl>
      {report.nodes.map((node, index) => (
        <div key={index}>
          <p>
            {t(`vecStatus_${node.status}`)} · {node.reason}
          </p>
          <dl>
            <dt>{t("vecCounts")}</dt>
            <dd>
              {node.counts.input} / {node.counts.eligible} /{" "}
              {node.counts.failed} / {node.counts.truncated}
            </dd>
            <dt>{t("vecUsage")}</dt>
            <dd>
              {t("vecUsageValue", {
                requests: node.fake_requests,
                tokens: node.fake_usage,
                cost: node.fake_cost_nanos / 1e9,
              })}
            </dd>
          </dl>
        </div>
      ))}
      <details>
        <summary>{t("vecAudit")}</summary>
        {report.attempts.map((attempt) => (
          <p key={attempt.id}>
            <code>{attempt.id}</code> · {attempt.state} · {t("vecTokens")}:{" "}
            {attempt.usage ?? t("vecUnknown")} · {t("vecReserved")}:{" "}
            {t("vecCostValue", { cost: attempt.reserved_nanos / 1e9 })} ·{" "}
            {attempt.reason}
          </p>
        ))}
        {result.events.map((event) => (
          <div key={event.event_id}>
            <p>
              <code>{event.event_id}</code> · {event.operator} · {event.mode} ·{" "}
              {event.implementation} · {event.contract}
            </p>
            <ul>
              {event.inputs.map((ref) => (
                <li key={`${ref.asset_id}:${ref.version ?? ""}`}>
                  <code>
                    {ref.asset_id}@{ref.version}
                  </code>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </details>
    </section>
  );
}
