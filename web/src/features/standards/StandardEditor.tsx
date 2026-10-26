import { useState } from "react";

import { prepareStandard } from "../../api/standards";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { PlanCard } from "../actions/PlanCard";

import { StandardConstraints } from "./StandardConstraints";
import { sensitivityLabels, standardStatuses } from "./values";

import type { FieldStandard } from "../../api/standards";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function StandardEditor({
  definition,
  onChanged,
  onOpenReceipt,
}: {
  definition: FieldStandard;
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
      setPlan(await prepareStandard(draft));
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
            {(
              [
                ["name_zh", "stdNameZh"],
                ["name_en", "stdNameEn"],
                ["description", "stdDefinition"],
                ["data_type", "stdType"],
                ["owner", "stdOwner"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {t(label)}
                <input
                  required={key !== "owner"}
                  value={draft[key]}
                  onChange={(event) => {
                    setDraft({ ...draft, [key]: event.target.value });
                  }}
                />
              </label>
            ))}
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
            <label>
              {t("stdSensitivity")}
              <select
                value={draft.sensitivity}
                onBlur={(event) => {
                  const sensitivity = Object.keys(sensitivityLabels).find(
                    (key): key is keyof typeof sensitivityLabels =>
                      key === event.target.value,
                  );
                  if (sensitivity) setDraft({ ...draft, sensitivity });
                }}
                onChange={(event) => {
                  const sensitivity = Object.keys(sensitivityLabels).find(
                    (key): key is keyof typeof sensitivityLabels =>
                      key === event.target.value,
                  );
                  if (sensitivity) setDraft({ ...draft, sensitivity });
                }}
              >
                {Object.entries(sensitivityLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("stdAliases")}
              <input
                value={draft.aliases.join(", ")}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    aliases: event.target.value
                      .split(",")
                      .map((value) => value.trim())
                      .filter(Boolean),
                  });
                }}
              />
            </label>
          </div>
          <StandardConstraints draft={draft} onChange={setDraft} />
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
