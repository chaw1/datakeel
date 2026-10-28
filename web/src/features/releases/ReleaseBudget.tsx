import { useI18n } from "../../i18n/useI18n";

const GIB = 1024 ** 3;

export interface BudgetDraft {
  objects: string;
  gib: string;
}

export const emptyBudget: BudgetDraft = { objects: "", gib: "" };

/** Build the optional budget query; empty fields keep the server default. */
export function budgetQuery(draft: BudgetDraft): string {
  const query = new URLSearchParams();
  const objects = Number(draft.objects);
  const gib = Number(draft.gib);
  if (draft.objects.trim() && Number.isFinite(objects))
    query.set("max_objects", String(Math.round(objects)));
  if (draft.gib.trim() && Number.isFinite(gib))
    query.set("max_bytes", String(Math.round(gib * GIB)));
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export function ReleaseBudget({
  value,
  onChange,
}: {
  value: BudgetDraft;
  onChange: (value: BudgetDraft) => void;
}) {
  const { t } = useI18n();
  return (
    <fieldset className="release-budget">
      <legend>{t("releaseBudget")}</legend>
      <p className="muted">{t("releaseBudgetHint")}</p>
      <label>
        {t("releaseBudgetObjects")}
        <input
          type="number"
          min={1}
          step={1}
          inputMode="numeric"
          value={value.objects}
          onChange={(event) => {
            onChange({ ...value, objects: event.target.value });
          }}
        />
      </label>
      <label>
        {t("releaseBudgetGib")}
        <input
          type="number"
          min={0}
          step="any"
          inputMode="decimal"
          value={value.gib}
          onChange={(event) => {
            onChange({ ...value, gib: event.target.value });
          }}
        />
      </label>
    </fieldset>
  );
}
