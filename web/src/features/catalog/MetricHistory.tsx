import { useRef, useState } from "react";

import { post } from "../../api/client";
import { localizedCatalogName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { PlanCard } from "../actions/PlanCard";

import type { MetricHistory as History } from "../../api/objects";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

import "./catalog.css";

export function MetricHistory({
  history,
  currentVersion,
  onChanged,
  onOpenReceipt,
}: {
  history: History;
  currentVersion: number;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function prepare(version: number) {
    if (pending.current || isComposing() || version === currentVersion) return;
    pending.current = true;
    setBusy(true);
    setPlan(null);
    setError("");
    setSaved(false);
    try {
      setPlan(
        await post<ActionPlan>("/api/actions/rollback_metric/prepare", {
          metric_id: history.metric_id,
          version,
        }),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t("catRollbackFailed"),
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="object-revisions">
      <h2>
        {t("objMetricHistory")} · {history.versions.length}
      </h2>
      <p className="muted">{t("catRollbackIntro")}</p>
      {history.versions.map((card) => (
        <article
          className="metric-history-version"
          data-metric-version={card.definition.version}
          key={card.definition.version}
        >
          <details>
            <summary>
              {t("version")} {card.definition.version} ·{" "}
              {localizedCatalogName(card.definition.name, t)}
            </summary>
            <pre>{JSON.stringify(card.definition, null, 2)}</pre>
          </details>
          {card.definition.version === currentVersion ? (
            <span className="badge green">{t("catCurrentVersion")}</span>
          ) : (
            <button
              type="button"
              className="button subtle"
              disabled={busy}
              onKeyDown={(event) => {
                if (isComposing(event.nativeEvent)) event.preventDefault();
              }}
              onClick={() => {
                void prepare(card.definition.version);
              }}
            >
              {t("catRollbackVersion")}
            </button>
          )}
        </article>
      ))}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className="catalog-success" role="status">
          {t("catChangeSaved")}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={(target) => {
            onOpenReceipt({ ...target, includeCatalog: true });
          }}
          onInvalidated={onChanged}
          onResolved={(run) => {
            if (run?.status === "SUCCEEDED") {
              setSaved(true);
              onChanged();
            }
          }}
        />
      )}
    </section>
  );
}
