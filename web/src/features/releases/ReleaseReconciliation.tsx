import { useState } from "react";

import { post } from "../../api/client";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import type { components } from "../../api/generated";
import type { MessageKey } from "../../i18n/en";

type Report = components["schemas"]["ReconcileReport"];
const labels: Record<Report["categories"][number]["name"], MessageKey> = {
  file_count: "reconcileFileCount",
  bytes: "reconcileBytes",
  hashes: "reconcileHashes",
  annotations: "reconcileAnnotations",
  metadata: "reconcileMetadata",
  lineage: "reconcileLineage",
};

export function ReleaseReconciliation({ releaseId }: { releaseId: string }) {
  const { t, locale } = useI18n();
  const base = `/api/releases/${encodeURIComponent(releaseId)}`;
  const history = useResource<Report[]>(`${base}/reconciliations`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function reconcile() {
    setBusy(true);
    setError("");
    try {
      await post<Report>(`${base}/reconcile`, {});
      history.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={t("reconcileHistory")}>
      <div className="card-heading">
        <h4>{t("reconcileHistory")}</h4>
        <button
          className="button"
          disabled={busy}
          onClick={() => void reconcile()}
        >
          {t("reconcileRun")}
        </button>
      </div>
      <p className="muted">{t("reconcileStoredHint")}</p>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      <ResourceState {...history} onRetry={history.reload} />
      {history.value && !history.value.length && <p>{t("reconcileEmpty")}</p>}
      {history.value?.map((report) => (
        <details key={report.id} open>
          <summary>
            {date(report.created_at, locale)} ·{" "}
            {t(report.passed ? "reconcilePassed" : "reconcileFailed")}
          </summary>
          {report.categories.map((category) => (
            <section className="reconcile-category" key={category.name}>
              <h5>
                {t(labels[category.name])} ·{" "}
                {t(category.passed ? "reconcilePassed" : "reconcileFailed")}
              </h5>
              {category.differences.map((difference, index) => (
                <dl
                  className="version-summary"
                  key={`${difference.path}:${String(index)}`}
                >
                  <div>
                    <dt>{t("fileName")}</dt>
                    <dd>{difference.path}</dd>
                  </div>
                  <div>
                    <dt>{t("reconcileExpected")}</dt>
                    <dd>
                      <code>{JSON.stringify(difference.expected)}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>{t("reconcileActual")}</dt>
                    <dd>
                      <code>{JSON.stringify(difference.actual)}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>{t("reconcileReason")}</dt>
                    <dd>{difference.reason}</dd>
                  </div>
                </dl>
              ))}
            </section>
          ))}
        </details>
      ))}
    </section>
  );
}
