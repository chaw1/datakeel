import { useState } from "react";

import { prepareMetric, tablePath } from "../../api/catalog";
import { ResourceState } from "../../components/ResourceState";
import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";
import { PlanCard } from "../actions/PlanCard";

import { MetricFilters } from "./MetricFilters";

import type {
  CatalogTableDetail,
  MetricCard,
  MetricDefinition,
} from "../../api/catalog";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

const aggregations = [
  ["sum", "catSum"],
  ["count", "catCountRows"],
  ["count_distinct", "catDistinctCount"],
  ["avg", "catAverage"],
  ["min", "catMinimum"],
  ["max", "catMaximum"],
] as const;

export function MetricEditor({
  card,
  onChanged,
  onOpenReceipt,
}: {
  card: MetricCard;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const isComposing = useCompositionGuard();
  const [draft, setDraft] = useState<MetricDefinition>(card.definition);
  const [synonymText, setSynonymText] = useState(
    (card.definition.synonyms ?? []).join(", "),
  );
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const fields = useResource<CatalogTableDetail>(
    tablePath(card.definition.measure.table),
  );
  async function prepare() {
    if (busy || isComposing()) return;
    setBusy(true);
    setError("");
    try {
      setPlan(
        await prepareMetric({
          ...draft,
          synonyms: synonymText
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          version: card.definition.version,
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("catEditFailed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="catalog-editor" aria-label={t("catEdit")}>
      <p className="muted">{t("catEditIntro")}</p>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!plan && (
        <form
          onKeyDownCapture={(event) => {
            if (event.key === "Enter" && isComposing(event.nativeEvent))
              event.preventDefault();
          }}
          onSubmit={(event) => {
            event.preventDefault();
            void prepare();
          }}
        >
          <div className="catalog-form-grid">
            <label>
              {t("catName")}
              <input
                required
                value={draft.name}
                onChange={(event) => {
                  setDraft({ ...draft, name: event.target.value });
                }}
              />
            </label>
            <label>
              {t("catOwner")}
              <input
                required
                value={draft.owner}
                onChange={(event) => {
                  setDraft({ ...draft, owner: event.target.value });
                }}
              />
            </label>
            <label className="catalog-full-row">
              {t("catDefinition")}
              <textarea
                required
                rows={3}
                value={draft.description}
                onChange={(event) => {
                  setDraft({ ...draft, description: event.target.value });
                }}
              />
            </label>
            <label>
              {t("catAmountField")}
              <select
                value={draft.measure.column}
                onBlur={(event) => {
                  if (draft.measure.column !== event.target.value)
                    setDraft({
                      ...draft,
                      measure: { ...draft.measure, column: event.target.value },
                    });
                }}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    measure: { ...draft.measure, column: event.target.value },
                  });
                }}
              >
                {!fields.value?.columns.some(
                  (item) => item.asset_ref.asset_id === draft.measure.column,
                ) && (
                  <option value={draft.measure.column}>
                    {draft.measure.column}
                  </option>
                )}
                {fields.value?.columns.map((item) => (
                  <option
                    key={item.asset_ref.asset_id}
                    value={item.asset_ref.asset_id}
                  >
                    {localizedObjectName(
                      item.asset_ref.asset_type,
                      item.name,
                      locale,
                    )}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("catAggregation")}
              <select
                value={draft.measure.aggregation}
                onBlur={(event) => {
                  const aggregation = aggregations.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (aggregation && aggregation !== draft.measure.aggregation)
                    setDraft({
                      ...draft,
                      measure: { ...draft.measure, aggregation },
                    });
                }}
                onChange={(event) => {
                  const aggregation = aggregations.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (aggregation)
                    setDraft({
                      ...draft,
                      measure: { ...draft.measure, aggregation },
                    });
                }}
              >
                {aggregations.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            <label className="catalog-full-row">
              {t("catSynonyms")}
              <input
                value={synonymText}
                onChange={(event) => {
                  setSynonymText(event.target.value);
                }}
              />
            </label>
            <label className="catalog-full-row">
              {t("catCaveats")}
              <textarea
                rows={2}
                value={(draft.caveats ?? []).join("\n")}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    caveats: event.target.value.split("\n"),
                  });
                }}
              />
            </label>
          </div>
          <ResourceState
            loading={fields.loading}
            error={fields.error}
            onRetry={fields.reload}
          />
          <MetricFilters
            filters={draft.filters ?? []}
            table={draft.measure.table}
            onChange={(filters) => {
              setDraft({ ...draft, filters });
            }}
          />
          <button
            className="button"
            type="submit"
            disabled={busy}
            onKeyDown={(event) => {
              if (isComposing(event.nativeEvent)) event.preventDefault();
            }}
          >
            {t(busy ? "catPreparing" : "catPrepare")}
          </button>
        </form>
      )}
      {saved && (
        <p role="status" className="catalog-success">
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
