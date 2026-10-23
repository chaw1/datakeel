import { useI18n } from "../../i18n/useI18n";

import type { ConversationCreate } from "../../api/types";

type Budget = NonNullable<ConversationCreate["budget"]>;
export function BudgetFields({
  value,
  onChange,
  disabled,
}: {
  value: Budget;
  onChange: (value: Budget) => void;
  disabled: boolean;
}) {
  const { t } = useI18n();
  const fields = [
    ["conversation_tokens", "conversationTokenLimit"],
    ["daily_tokens", "dailyTokenLimit"],
    ["conversation_usd", "conversationUsdLimit"],
    ["daily_usd", "dailyUsdLimit"],
  ] as const;
  return (
    <details className="budget-fields">
      <summary>{t("conversationBudget")}</summary>
      {fields.map(([key, label]) => (
        <label key={key}>
          {t(label)}
          <input
            type="number"
            min={key.endsWith("_tokens") ? 1 : 0.000001}
            step={key.endsWith("_tokens") ? 1 : "any"}
            value={value[key]}
            disabled={disabled}
            onChange={(event) => {
              const next = Number(event.target.value);
              if (
                Number.isFinite(next) &&
                next > 0 &&
                (!key.endsWith("_tokens") || Number.isInteger(next))
              )
                onChange({ ...value, [key]: next });
            }}
          />
        </label>
      ))}
    </details>
  );
}
