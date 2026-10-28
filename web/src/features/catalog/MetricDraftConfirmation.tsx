import { useState } from "react";

import { post } from "../../api/client";
import { useI18n } from "../../i18n/useI18n";
import { PlanCard } from "../actions/PlanCard";

import type { CatalogObject, MetricDefinition } from "../../api/catalog";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function MetricDraftConfirmation({
  item,
  onChanged,
  onOpenReceipt,
}: {
  item: CatalogObject;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [definition, setDefinition] = useState(
    item.properties?.definition
      ? JSON.stringify(item.properties.definition, null, 2)
      : "",
  );
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const confirmed = saved || item.properties?.status === "confirmed";
  const deleted = item.properties?.source_deleted === true;
  async function prepare() {
    setBusy(true);
    setError("");
    try {
      const parsed: unknown = definition.trim()
        ? JSON.parse(definition)
        : undefined;
      if (
        parsed !== undefined &&
        (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      )
        throw new Error(t("metadataDefinitionInvalid"));
      setPlan(
        await post<ActionPlan>("/api/actions/confirm_metric_draft/prepare", {
          draft_id: item.asset_ref.asset_id,
          definition: parsed as MetricDefinition | undefined,
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="catalog-editor" aria-label={t("metadataConfirmDraft")}>
      <p>{t("metadataDraftNotice")}</p>
      {deleted && <p role="status">{t("metadataDeleted")}</p>}
      {confirmed && <p role="status">{t("metadataDraftConfirmed")}</p>}
      {!plan && !confirmed && !deleted && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void prepare();
          }}
        >
          <label>
            {t("metadataDefinitionJson")}
            <textarea
              rows={12}
              value={definition}
              disabled={busy}
              onChange={(event) => {
                setDefinition(event.target.value);
              }}
            />
          </label>
          <button className="button primary" disabled={busy} type="submit">
            {t("metadataConfirmDraft")}
          </button>
        </form>
      )}
      {error && <p role="alert">{error}</p>}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={onOpenReceipt}
          onInvalidated={onChanged}
          onResolved={(run) => {
            if (run?.status === "SUCCEEDED") {
              setSaved(true);
              onChanged();
            }
          }}
        />
      )}
      <details>
        <summary>{t("metadataDetails")}</summary>
        <pre>{JSON.stringify(item.properties, null, 2)}</pre>
      </details>
    </section>
  );
}
