import { useState } from "react";

import { post } from "../../api/client";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";
import { PlanCard } from "../actions/PlanCard";

import type { StandardsHistory as History } from "../../api/standards";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function StandardsHistory({
  onChanged,
  onOpenReceipt,
}: {
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const composing = useCompositionGuard();
  const resource = useResource<History>("/api/standards/history");
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const revisions = resource.value?.revisions ?? [];
  async function prepare(revision: number) {
    if (busy || composing()) return;
    setBusy(true);
    setError("");
    try {
      setPlan(
        await post<ActionPlan>("/api/actions/rollback_standards/prepare", {
          revision,
        }),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t("stdPrepareFailed"),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card standards-section">
      <p>{t("stdHistoryIntro")}</p>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={onOpenReceipt}
          onInvalidated={onChanged}
          onResolved={(run) => {
            if (run?.status === "SUCCEEDED") onChanged();
          }}
        />
      )}
      {[...revisions].reverse().map((item) => (
        <article className="metric-history-version" key={item.revision}>
          <h2>{t("stdRevision", { revision: item.revision })}</h2>
          <p>
            {date(item.created_at, locale)} · {item.actor} ·{" "}
            <code>{item.action_type}</code>
          </p>
          <details>
            <summary>
              {t("stdFields")} · {item.contract?.standards.length ?? 0},{" "}
              {t("stdCodes")} · {item.contract?.code_lists.length ?? 0}
            </summary>
            <pre>
              {JSON.stringify(
                { contract: item.contract, mappings: item.mappings },
                null,
                2,
              )}
            </pre>
          </details>
          {item.revision === revisions.at(-1)?.revision ? (
            <span className="badge green">{t("stdCurrentRevision")}</span>
          ) : (
            <button
              className="button subtle"
              disabled={busy}
              onKeyDown={(event) => {
                if (composing(event.nativeEvent)) event.preventDefault();
              }}
              onClick={() => {
                void prepare(item.revision);
              }}
            >
              {t("stdRollback")}
            </button>
          )}
        </article>
      ))}
      {!resource.loading && !revisions.length && <p>{t("stdNoHistory")}</p>}
    </section>
  );
}
