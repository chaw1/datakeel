import { Badge, Surface } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import type { CustomOperatorRun } from "../../api/customOperators";

export function OperatorRunHistory({ runs }: { runs: CustomOperatorRun[] }) {
  const { t, locale } = useI18n();
  return (
    <section aria-label={t("customOperatorRuns")}>
      <h2>{t("customOperatorRuns")}</h2>
      {!runs.length && <p className="muted">{t("customOperatorNoRuns")}</p>}
      <div className="custom-run-history">
        {runs.map((run) => (
          <Surface
            as="article"
            className="custom-run-record"
            key={run.id}
            data-custom-run={run.id}
          >
            <header className="section-heading">
              <h3>
                <code>{run.operator}</code>
              </h3>
              <Badge tone={run.success ? "ok" : "danger"}>
                {t(run.success ? "SUCCEEDED" : "FAILED")}
              </Badge>
            </header>
            <p className="muted">{date(run.completed_at, locale)}</p>
            <dl className="approval-fields">
              <div>
                <dt>{t("customOperatorBackend")}</dt>
                <dd>{run.backend}</dd>
              </div>
              <div>
                <dt>{t("customOperatorExitReason")}</dt>
                <dd>{run.exit_reason}</dd>
              </div>
              <div>
                <dt>{t("customOperatorHash")}</dt>
                <dd>
                  <code>{run.code_hash}</code>
                </dd>
              </div>
              <div>
                <dt>{t("customOperatorImageDigest")}</dt>
                <dd>
                  <code>{run.image_digest}</code>
                </dd>
              </div>
              <div>
                <dt>{t("customOperatorParamDigest")}</dt>
                <dd>
                  <code>{run.params_digest}</code>
                </dd>
              </div>
              <div>
                <dt>{t("customOperatorResources")}</dt>
                <dd>
                  <pre>{JSON.stringify(run.resources, null, 2)}</pre>
                </dd>
              </div>
            </dl>
            <details>
              <summary>{t("customOperatorFullRecord")}</summary>
              <pre className="custom-source">
                {JSON.stringify(run, null, 2)}
              </pre>
            </details>
          </Surface>
        ))}
      </div>
    </section>
  );
}
