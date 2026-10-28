import { useState } from "react";

import { prepareCodeList } from "../../api/standards";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { PlanCard } from "../actions/PlanCard";

import { CodeEntriesEditor } from "./CodeEntriesEditor";
import { standardStatuses } from "./values";

import type { CodeList } from "../../api/standards";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function CodeListEditor({
  definition,
  onChanged,
  onOpenReceipt,
}: {
  definition: CodeList;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const composing = useCompositionGuard();
  const [draft, setDraft] = useState(definition);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare() {
    if (busy || composing()) return;
    setBusy(true);
    setError("");
    try {
      setPlan(await prepareCodeList(draft));
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t("stdPrepareFailed"),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="catalog-editor" aria-label={t("stdEdit")}>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!plan && (
        <form
          onKeyDownCapture={(event) => {
            if (event.key === "Enter" && composing(event.nativeEvent))
              event.preventDefault();
          }}
          onSubmit={(event) => {
            event.preventDefault();
            void prepare();
          }}
        >
          <div className="catalog-form-grid">
            <label>
              {t("stdCode")}
              <input
                required
                disabled={definition.code !== ""}
                value={draft.code}
                onChange={(event) => {
                  setDraft({ ...draft, code: event.target.value });
                }}
              />
            </label>
            <label>
              {t("stdName")}
              <input
                required
                value={draft.name}
                onChange={(event) => {
                  setDraft({ ...draft, name: event.target.value });
                }}
              />
            </label>
            <label>
              {t("stdLifecycle")}
              <select
                value={draft.status}
                onBlur={(event) => {
                  const status = standardStatuses.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (status) setDraft({ ...draft, status });
                }}
                onChange={(event) => {
                  const status = standardStatuses.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (status) setDraft({ ...draft, status });
                }}
              >
                {standardStatuses.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <CodeEntriesEditor
            entries={draft.entries}
            onChange={(entries) => {
              setDraft({ ...draft, entries });
            }}
          />
          <button className="button" type="submit" disabled={busy}>
            {t(busy ? "planWorking" : "stdReview")}
          </button>
        </form>
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
    </section>
  );
}
